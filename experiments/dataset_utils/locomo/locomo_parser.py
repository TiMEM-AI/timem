"""
TiMem Locomo Dataset Parser and Splitter
Handles parsing and splitting of Locomo dataset into TiMem memory model format.
Provides dataset splitting, processing and formatting functionality.
"""
import json
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import re
from dataclasses import dataclass
import shutil

# Modified import path to use relative imports
try:
    from ...timem.models.memory import (
        Message, MessageRole, MemoryFragment, Memory, MemoryLevel,
        L1FragmentMemory, Entity, Relationship, KeyInformation, MemoryType
    )
    from ...timem.utils.logging import get_logger
except ImportError:
    # Provide a simple logger if running in standalone environment
    import logging

    def get_logger(name):
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    # Provide simplified memory model classes for standalone execution
    class MessageRole:
        USER = "user"
        ASSISTANT = "assistant"
        SYSTEM = "system"

    class Message:
        def __init__(self, role, content, timestamp=None, metadata=None):
            self.role = role
            self.content = content
            self.timestamp = timestamp or datetime.now().timestamp()
            self.metadata = metadata or {}

    class Entity:
        def __init__(self, name, type, attributes=None, extracted_from=None):
            self.name = name
            self.type = type
            self.attributes = attributes or {}
            self.extracted_from = extracted_from

    class KeyInformation:
        def __init__(self, content, type, importance=0.5):
            self.content = content
            self.type = type
            self.importance = importance

    class MemoryType:
        FACTUAL = "factual"
        EMOTIONAL = "emotional"
        DECISIONAL = "decisional"

    class L1FragmentMemory:
        def __init__(
            self,
            id,
            session_id,
            dialogue,
            summary="",
            keywords=None,
            key_information=None,
            entities=None,
            importance=0.5,
            temporal_position=0,
            created_at=None,
        ):
            self.id = id
            self.session_id = session_id
            self.dialogue = dialogue
            self.summary = summary
            self.keywords = keywords or []
            self.key_information = key_information or []
            self.entities = entities or []
            self.importance = importance
            self.temporal_position = temporal_position
            self.created_at = created_at or datetime.now().timestamp()

logger = get_logger(__name__)


@dataclass
class DialogueTurn:
    """Dialogue turn data class"""

    speaker: str
    dia_id: str
    text: str
    img_url: Optional[List[str]] = None
    blip_caption: Optional[str] = None
    query: Optional[str] = None


@dataclass
class ConversationSession:
    """Conversation session data class"""

    sample_id: str
    session_id: str
    date_time: str
    speaker_a: str
    speaker_b: str
    dialogues: List[DialogueTurn]
    total_turns: int


class LocomoParser:
    """
    Locomo Dataset Parser and Splitter

    Handles parsing Locomo dataset dialogue data and converting to TiMem memory model format.
    Also provides dataset splitting functionality from raw JSON to organized session files.

    In addition to the per-session split files, this parser also generates:
      - data/locomo_experiment_metadata.json
    which is required by experiments/datasets/locomo/01_memory_generation.py.
    """

    def __init__(self, data_dir: str = "data/locomo10_smart_split"):
        """
        Initialize parser

        Args:
            data_dir: Locomo dataset directory path
        """
        self.data_dir = Path(data_dir)
        self.logger = logger

        # Create directory if it doesn't exist (for splitting)
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created Locomo data directory: {self.data_dir}")

        self.logger.info(f"Initialized Locomo parser, data directory: {self.data_dir}")

    def split_dataset_from_json(self, raw_json_path: str, output_dir: str = None) -> bool:
        """
        Split raw Locomo JSON file into organized session files

        Args:
            raw_json_path: Path to raw locomo10.json file
            output_dir: Output directory (default: self.data_dir)

        Returns:
            True if successful, False otherwise
        """
        if output_dir is None:
            output_dir = self.data_dir
        else:
            output_dir = Path(output_dir)

        raw_json_path = Path(raw_json_path)

        if not raw_json_path.exists():
            self.logger.error(f"Raw JSON file not found: {raw_json_path}")
            return False

        self.logger.info(f"Starting Locomo dataset splitting from {raw_json_path} to {output_dir}")

        try:
            # Load raw JSON data
            with open(raw_json_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            # Validate data structure
            if not isinstance(raw_data, list):
                self.logger.error("Raw data must be a list of entries")
                return False

            self.logger.info(f"Loaded raw data with {len(raw_data)} entries")

            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)

            # Process each conversation entry
            total_files = 0
            skipped_entries = 0

            for conv_idx, conversation in enumerate(raw_data):
                try:
                    # Validate conversation structure
                    if not isinstance(conversation, dict):
                        skipped_entries += 1
                        continue

                    # Extract conversation metadata
                    sample_id = conversation.get("sample_id")

                    if sample_id is None:
                        # Use index as fallback
                        sample_id = str(conv_idx + 1)
                    else:
                        sample_id = str(sample_id)

                    # Get conversation data (contains sessions)
                    conv_data = conversation.get("conversation", {})
                    if not isinstance(conv_data, dict):
                        continue

                    speaker_a = conv_data.get("speaker_a", "")
                    speaker_b = conv_data.get("speaker_b", "")

                    # Process each session in the conversation
                    for session_key, session_data in conv_data.items():
                        # Skip non-session fields (only process session_X keys)
                        if not session_key.startswith("session_") or "_date_time" in session_key:
                            continue

                        # Extract session number from key (e.g., "session_1" -> "1")
                        session_num = session_key.replace("session_", "")

                        # Get corresponding date_time
                        date_time_key = f"session_{session_num}_date_time"
                        date_time = conv_data.get(date_time_key, "")

                        # Validate session data
                        if not isinstance(session_data, list):
                            continue

                        # Create session file data
                        session_file_data = {
                            "sample_id": f"conv-{sample_id}" if not str(sample_id).startswith("conv-") else str(sample_id),
                            "session_id": f"session_{session_num}",
                            "date_time": date_time,
                            "speaker_a": speaker_a,
                            "speaker_b": speaker_b,
                            "dialogues": session_data,
                            "total_turns": len(session_data),
                        }

                        # Create filename: locomo10_timem_conv-26_session_1.json
                        conv_prefix = session_file_data["sample_id"]
                        filename = f"locomo10_timem_{conv_prefix}_session_{session_num}.json"
                        file_path = output_dir / filename

                        # Save session data
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(session_file_data, f, ensure_ascii=False, indent=2)

                        total_files += 1
                        self.logger.debug(f"Saved session file: {filename}")

                except Exception as e:
                    self.logger.warning(f"Skipping invalid conversation {conv_idx}: {e}")
                    skipped_entries += 1
                    continue

            if skipped_entries > 0:
                self.logger.warning(f"Skipped {skipped_entries} invalid conversations")

            self.logger.info(f"Successfully split dataset into {total_files} session files")

            # Generate additional files (QA, categories, fields, metadata)
            self._generate_additional_files(raw_data, output_dir, total_files)

            # Generate experiment metadata for experiments/datasets/locomo/01_memory_generation.py
            # Always write into the project-level data/ directory (not inside output_dir)
            self._generate_experiment_metadata(raw_data, output_dir)

            self.logger.info(f"Output directory: {output_dir}")

            # Update data_dir to point to the split directory
            self.data_dir = output_dir

            return True

        except Exception as e:
            self.logger.error(f"Dataset splitting failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _generate_additional_files(self, raw_data: List[Dict], output_dir: Path, total_session_files: int):
        """Generate additional files: QA, categories, fields, and metadata"""
        try:
            self.logger.info("Generating additional files (QA, categories, fields, metadata)...")

            # Collect all QA data from raw conversations
            all_qa_data = []
            all_conversations = []
            all_session_summaries = []
            all_event_summaries = []
            all_observations = []

            for conversation in raw_data:
                sample_id = conversation.get("sample_id", "unknown")

                # Extract QA data
                qa_data = conversation.get("qa", [])
                for qa_item in qa_data:
                    qa_entry = {
                        "qa": qa_item,
                        "source_record": sample_id,
                    }
                    all_qa_data.append(qa_entry)

                # Extract conversation data
                conv_data = conversation.get("conversation", {})
                if conv_data:
                    conv_entry = {
                        "sample_id": sample_id,
                        "conversation": conv_data,
                    }
                    all_conversations.append(conv_entry)

                # Extract session summaries
                session_summary = conversation.get("session_summary", {})
                if session_summary:
                    summary_entry = {
                        "sample_id": sample_id,
                        "session_summary": session_summary,
                    }
                    all_session_summaries.append(summary_entry)

                # Extract event summaries
                event_summary = conversation.get("event_summary", {})
                if event_summary:
                    event_entry = {
                        "sample_id": sample_id,
                        "event_summary": event_summary,
                    }
                    all_event_summaries.append(event_entry)

                # Extract observations
                observation = conversation.get("observation", {})
                if observation:
                    obs_entry = {
                        "sample_id": sample_id,
                        "observation": observation,
                    }
                    all_observations.append(obs_entry)

            # Generate QA files by category (qa_001 to qa_004)
            self._generate_qa_category_files(all_qa_data, output_dir)

            # Generate category files (cat_01 to cat_05)
            self._generate_category_files(all_qa_data, output_dir)

            # Generate field files
            self._generate_field_files(
                all_qa_data,
                all_conversations,
                all_session_summaries,
                all_event_summaries,
                all_observations,
                output_dir,
            )

            # Generate metadata file
            self._generate_metadata_file(output_dir, total_session_files)

            self.logger.info("Successfully generated all additional files")

        except Exception as e:
            self.logger.error(f"Failed to generate additional files: {e}")
            import traceback

            traceback.print_exc()

    def _generate_qa_category_files(self, all_qa_data: List[Dict], output_dir: Path):
        """Generate locomo10_qa_001.json to locomo10_qa_004.json files"""
        # Group QA data by category
        qa_by_category = {1: [], 2: [], 3: [], 4: []}

        for qa_entry in all_qa_data:
            category = qa_entry.get("qa", {}).get("category", 1)
            if category in qa_by_category:
                qa_by_category[category].append(qa_entry)

        # Save each category to separate files
        for category, qa_items in qa_by_category.items():
            if qa_items:  # Only create file if there are items
                filename = f"locomo10_qa_{category:03d}.json"
                file_path = output_dir / filename

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(qa_items, f, ensure_ascii=False, indent=2)

                self.logger.debug(f"Generated {filename} with {len(qa_items)} QA items")

    def _generate_category_files(self, all_qa_data: List[Dict], output_dir: Path):
        """Generate locomo10_cat_01.json to locomo10_cat_05.json files"""
        # Group QA data by category for cat files (same as qa files but different naming)
        cat_by_category = {1: [], 2: [], 3: [], 4: [], 5: []}

        for qa_entry in all_qa_data:
            category = qa_entry.get("qa", {}).get("category", 1)
            if category in cat_by_category:
                cat_by_category[category].append(qa_entry)

        # Save each category to separate files
        for category, qa_items in cat_by_category.items():
            if qa_items:  # Only create file if there are items
                filename = f"locomo10_cat_{category:02d}.json"
                file_path = output_dir / filename

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(qa_items, f, ensure_ascii=False, indent=2)

                self.logger.debug(f"Generated {filename} with {len(qa_items)} QA items")

    def _generate_field_files(
        self,
        all_qa_data: List[Dict],
        all_conversations: List[Dict],
        all_session_summaries: List[Dict],
        all_event_summaries: List[Dict],
        all_observations: List[Dict],
        output_dir: Path,
    ):
        """Generate locomo10_field_*.json files"""

        # Generate field_qa.json - QA data grouped by sample_id
        qa_by_sample = {}
        for qa_entry in all_qa_data:
            sample_id = qa_entry.get("source_record", "unknown")
            if sample_id not in qa_by_sample:
                qa_by_sample[sample_id] = {
                    "sample_id": sample_id,
                    "qa": [],
                }
            qa_by_sample[sample_id]["qa"].append(qa_entry["qa"])

        field_qa_data = list(qa_by_sample.values())
        with open(output_dir / "locomo10_field_qa.json", 'w', encoding='utf-8') as f:
            json.dump(field_qa_data, f, ensure_ascii=False, indent=2)

        # Generate other field files
        if all_conversations:
            with open(output_dir / "locomo10_field_conversation.json", 'w', encoding='utf-8') as f:
                json.dump(all_conversations, f, ensure_ascii=False, indent=2)

        if all_session_summaries:
            with open(output_dir / "locomo10_field_session_summary.json", 'w', encoding='utf-8') as f:
                json.dump(all_session_summaries, f, ensure_ascii=False, indent=2)

        if all_event_summaries:
            with open(output_dir / "locomo10_field_event_summary.json", 'w', encoding='utf-8') as f:
                json.dump(all_event_summaries, f, ensure_ascii=False, indent=2)

        if all_observations:
            with open(output_dir / "locomo10_field_observation.json", 'w', encoding='utf-8') as f:
                json.dump(all_observations, f, ensure_ascii=False, indent=2)

        self.logger.debug("Generated all field files")

    def _generate_metadata_file(self, output_dir: Path, total_session_files: int):
        """Generate split_metadata.json file"""

        # Collect information about all generated files
        files_info = []

        # Add session files
        for session_file in output_dir.glob("locomo10_timem_*.json"):
            file_size = session_file.stat().st_size
            files_info.append(
                {
                    "filename": session_file.name,
                    "path": str(session_file),
                    "size_bytes": file_size,
                }
            )

        # Create metadata
        metadata = {
            "original_file": "data/locomo10.json",
            "split_methods": ["timem"],
            "total_files": total_session_files,
            "files": files_info,
        }

        with open(output_dir / "split_metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        self.logger.debug("Generated split_metadata.json")

    def _generate_experiment_metadata(self, raw_data: List[Dict[str, Any]], output_dir: Path) -> None:
        """Generate data/locomo_experiment_metadata.json matching the required schema."""

        try:
            project_root = Path(__file__).parent.parent.parent
            out_path = project_root / "data" / "locomo_experiment_metadata.json"

            conversations_meta: Dict[str, Any] = {}
            total_sessions = 0
            total_turns = 0

            for conv_idx, conversation in enumerate(raw_data):
                if not isinstance(conversation, dict):
                    continue

                sample_id = conversation.get("sample_id")
                if sample_id is None:
                    # Fallback to index-based id if missing
                    sample_id = str(conv_idx + 1)
                else:
                    sample_id = str(sample_id)

                conv_id = f"conv-{sample_id}" if not str(sample_id).startswith("conv-") else str(sample_id)

                conv_data = conversation.get("conversation", {})
                if not isinstance(conv_data, dict):
                    continue

                speaker_a = conv_data.get("speaker_a", "")
                speaker_b = conv_data.get("speaker_b", "")

                sessions: List[Dict[str, Any]] = []

                # Collect sessions for this conversation
                for session_key, session_dialogues in conv_data.items():
                    if not isinstance(session_key, str):
                        continue
                    if not session_key.startswith("session_") or "_date_time" in session_key:
                        continue

                    session_num = session_key.replace("session_", "")
                    session_id = f"session_{session_num}"
                    date_time = conv_data.get(f"session_{session_num}_date_time", "")

                    # file name & path follow splitter output naming
                    filename = f"locomo10_timem_{conv_id}_session_{session_num}.json"
                    session_file_path = output_dir / filename

                    # Determine turns count from split file if exists, otherwise from raw list length
                    turns_count = len(session_dialogues) if isinstance(session_dialogues, list) else 0

                    file_size = 0
                    if session_file_path.exists():
                        try:
                            file_size = session_file_path.stat().st_size
                            # Prefer the written file's total_turns if present
                            with open(session_file_path, "r", encoding="utf-8") as f:
                                written = json.load(f)
                            turns_count = int(written.get("total_turns", turns_count))
                        except Exception:
                            pass

                    sessions.append(
                        {
                            "sample_id": conv_id,
                            "session_id": session_id,
                            "date_time": date_time,
                            "speaker_a": speaker_a,
                            "speaker_b": speaker_b,
                            "total_turns": turns_count,
                            "file_path": str(Path("data") / "locomo10_smart_split" / filename).replace("/", "\\"),
                            "file_size": file_size,
                        }
                    )

                if not sessions:
                    continue

                # Sort sessions by numeric id
                def _sess_num(s):
                    try:
                        return int(str(s["session_id"]).split("_")[-1])
                    except Exception:
                        return 0

                sessions.sort(key=_sess_num)

                conv_total_sessions = len(sessions)
                conv_total_turns = sum(int(s.get("total_turns", 0)) for s in sessions)

                session_nums = [_sess_num(s) for s in sessions]
                session_range = [min(session_nums), max(session_nums)] if session_nums else [1, conv_total_sessions]

                date_values = [s.get("date_time", "") for s in sessions if s.get("date_time")]
                date_range = [date_values[0], date_values[-1]] if date_values else ["", ""]

                conversations_meta[conv_id] = {
                    "conv_id": conv_id,
                    "speakers": [speaker_a, speaker_b],
                    "total_sessions": conv_total_sessions,
                    "session_range": session_range,
                    "date_range": date_range,
                    "total_turns": conv_total_turns,
                    "sessions": sessions,
                }

                total_sessions += conv_total_sessions
                total_turns += conv_total_turns

            summary = {
                "total_conversations": len(conversations_meta),
                "total_sessions": total_sessions,
                "total_turns": total_turns,
                "avg_sessions_per_conv": (total_sessions / len(conversations_meta)) if conversations_meta else 0,
                "avg_turns_per_session": (total_turns / total_sessions) if total_sessions else 0,
            }

            payload = {
                "summary": summary,
                "conversations": conversations_meta,
            }

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.logger.info(f"Generated locomo experiment metadata: {out_path}")

        except Exception as e:
            self.logger.error(f"Failed to generate locomo experiment metadata: {e}")
            import traceback

            traceback.print_exc()

    def list_sessions(self) -> List[str]:
        """List all available session files"""
        session_files = []
        pattern = re.compile(r'locomo10_timem_conv-\d+_session_\d+\.json')

        for file_path in self.data_dir.glob("*.json"):
            if pattern.match(file_path.name):
                session_files.append(str(file_path))

        session_files.sort()
        self.logger.info(f"Found {len(session_files)} session files")
        return session_files

    def parse_session_file(self, file_path: str) -> Dict[str, Any]:
        """Parse a session JSON file"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Session file not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)

        return session_data


def get_dataset_parser(data_dir: str = "data/locomo10_smart_split") -> LocomoParser:
    """Backwards-compatible helper expected by dataset_utils.locomo.__init__.py."""
    return LocomoParser(data_dir)
