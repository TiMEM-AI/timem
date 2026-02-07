"""
LongMemEval Dataset Loader and Splitter
Handles loading and processing of LongMemEval-S dataset.
Provides dataset splitting functionality from raw JSON to organized directory structure.
"""
import json
import os
from typing import Dict, List, Set, Any, Optional, Tuple
from pathlib import Path
import shutil
from collections import defaultdict

class LongMemEvalSQuestionLoader:
    """LongMemEval-S Dataset Loader and Splitter"""
    
    def __init__(self, data_dir: str = "data/longmemeval_s_split"):
        self.data_dir = Path(data_dir)
        self.questions_dir = self.data_dir / "questions_by_user"
        self.sessions_dir = self.data_dir / "sessions_by_user"
        
        # Create directories if they don't exist (for splitting)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.questions_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def split_dataset_from_json(self, raw_json_path: str, output_dir: str = None) -> bool:
        """
        Split raw LongMemEval-S JSON file into organized directory structure
        
        Args:
            raw_json_path: Path to raw longmemeval_s_cleaned.json file
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
            print(f"❌ Raw JSON file not found: {raw_json_path}")
            return False
        
        print(f"\n{'='*80}")
        print(f"📂 Starting LongMemEval-S dataset splitting")
        print(f"{'='*80}")
        print(f"Input file: {raw_json_path}")
        print(f"Output directory: {output_dir}")
        
        try:
            # Load raw JSON data
            print(f"📖 Loading raw data...")
            with open(raw_json_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            # Validate data structure
            if not isinstance(raw_data, list):
                print(f"❌ Raw data must be a list of entries, got {type(raw_data)}")
                return False
            
            print(f"✅ Loaded raw data with {len(raw_data)} entries")
            
            # Create output directories
            output_dir.mkdir(parents=True, exist_ok=True)
            questions_output_dir = output_dir / "questions_by_user"
            sessions_output_dir = output_dir / "sessions_by_user"
            questions_output_dir.mkdir(parents=True, exist_ok=True)
            sessions_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Group data by user - LongMemEval-S uses question_id as user identifier
            users_data = defaultdict(lambda: {
                'sessions': [],
                'questions': []
            })
            
            skipped_entries = 0
            
            # Process each question entry in raw data
            for entry in raw_data:
                try:
                    # Validate entry structure
                    if not isinstance(entry, dict):
                        skipped_entries += 1
                        continue
                    
                    # Use question_id as user_id (each question represents a user scenario)
                    user_id = entry.get("question_id")
                    if not user_id:
                        skipped_entries += 1
                        continue
                    
                    # Convert to string for consistency
                    user_id = f"user_{str(user_id)}"
                    
                    # Extract haystack sessions (conversation history for this user)
                    haystack_sessions = entry.get("haystack_sessions", [])
                    if isinstance(haystack_sessions, list):
                        # Convert conversation turns to session format
                        for session_idx, session_turns in enumerate(haystack_sessions):
                            if isinstance(session_turns, list):
                                session_data = {
                                    "session_id": f"session_{session_idx + 1}",
                                    "user_id": user_id,
                                    "turns": session_turns,
                                    "session_date": entry.get("haystack_dates", [])[session_idx] if session_idx < len(entry.get("haystack_dates", [])) else ""
                                }
                                users_data[user_id]['sessions'].append(session_data)
                    
                    # Create question entry
                    question_entry = {
                        "question_id": entry.get("question_id"),
                        "question_type": entry.get("question_type"),
                        "question": entry.get("question"),
                        "question_date": entry.get("question_date"),
                        "answer": entry.get("answer"),
                        "answer_session_ids": entry.get("answer_session_ids", []),
                        "haystack_dates": entry.get("haystack_dates", []),
                        "haystack_session_ids": entry.get("haystack_session_ids", []),
                        "question_index": len(users_data[user_id]['questions']) + 1
                    }
                    
                    users_data[user_id]['questions'].append(question_entry)
                    
                except Exception as e:
                    print(f"⚠️ Skipping invalid entry: {e}")
                    skipped_entries += 1
                    continue
            
            if skipped_entries > 0:
                print(f"⚠️ Skipped {skipped_entries} invalid entries")
            
            print(f"📊 Found {len(users_data)} users")
            
            # Save sessions by user (format: user_001be529.json)
            sessions_saved = 0
            for user_id, data in users_data.items():
                if data['sessions']:
                    try:
                        # Sessions use format: user_001be529.json (no _sessions suffix)
                        sessions_file = sessions_output_dir / f"{user_id}.json"
                        with open(sessions_file, 'w', encoding='utf-8') as f:
                            json.dump(data['sessions'], f, ensure_ascii=False, indent=2)
                        sessions_saved += 1
                    except Exception as e:
                        print(f"❌ Failed to save sessions for {user_id}: {e}")
            
            # Save questions by user (format: user_001be529_questions.json)
            questions_saved = 0
            for user_id, data in users_data.items():
                if data['questions']:
                    try:
                        # Questions use format: user_001be529_questions.json
                        questions_file = questions_output_dir / f"{user_id}_questions.json"
                        with open(questions_file, 'w', encoding='utf-8') as f:
                            json.dump(data['questions'], f, ensure_ascii=False, indent=2)
                        questions_saved += 1
                    except Exception as e:
                        print(f"❌ Failed to save questions for {user_id}: {e}")
            
            # Generate additional directories and files
            self._generate_additional_longmemeval_files(users_data, output_dir)
            
            print(f"\n{'='*80}")
            print(f"📊 Dataset splitting completed")
            print(f"{'='*80}")
            print(f"Sessions files saved: {sessions_saved}")
            print(f"Questions files saved: {questions_saved}")
            print(f"Output directory: {output_dir}")
            print(f"{'='*80}\n")
            
            # Update directories to point to the split structure
            self.data_dir = output_dir
            self.questions_dir = questions_output_dir
            self.sessions_dir = sessions_output_dir
            
            return True
            
        except Exception as e:
            print(f"❌ Dataset splitting failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _generate_additional_longmemeval_files(self, users_data: dict, output_dir: Path):
        """Generate additional LongMemEval-S files and directories"""
        try:
            print("📂 Generating additional directories and files...")
            
            # Create additional directories
            questions_by_type_dir = output_dir / "questions_by_type"
            complete_data_by_type_dir = output_dir / "complete_data_by_type"
            complete_data_by_user_dir = output_dir / "complete_data_by_user"
            
            questions_by_type_dir.mkdir(exist_ok=True)
            complete_data_by_type_dir.mkdir(exist_ok=True)
            complete_data_by_user_dir.mkdir(exist_ok=True)
            
            # Collect all questions and group by type
            questions_by_type = defaultdict(list)
            complete_data_by_type = defaultdict(list)
            question_type_counts = defaultdict(int)
            
            for user_id, data in users_data.items():
                # Process questions
                for question in data['questions']:
                    question_type = question.get('question_type', 'unknown')
                    questions_by_type[question_type].append(question)
                    question_type_counts[question_type] += 1
                    
                    # Create complete data entry (question + sessions)
                    complete_entry = {
                        "user_id": user_id,
                        "question": question,
                        "sessions": data['sessions']
                    }
                    complete_data_by_type[question_type].append(complete_entry)
                
                # Save complete data by user
                if data['questions'] or data['sessions']:
                    user_complete_data = {
                        "user_id": user_id,
                        "questions": data['questions'],
                        "sessions": data['sessions']
                    }
                    
                    complete_user_file = complete_data_by_user_dir / f"{user_id}_complete.json"
                    with open(complete_user_file, 'w', encoding='utf-8') as f:
                        json.dump(user_complete_data, f, ensure_ascii=False, indent=2)
            
            # Save questions by type
            for question_type, questions in questions_by_type.items():
                type_file = questions_by_type_dir / f"{question_type}_questions.json"
                with open(type_file, 'w', encoding='utf-8') as f:
                    json.dump(questions, f, ensure_ascii=False, indent=2)
            
            # Save complete data by type
            for question_type, complete_data in complete_data_by_type.items():
                type_file = complete_data_by_type_dir / f"{question_type}_complete.json"
                with open(type_file, 'w', encoding='utf-8') as f:
                    json.dump(complete_data, f, ensure_ascii=False, indent=2)
            
            # Generate metadata.json
            self._generate_longmemeval_metadata(users_data, question_type_counts, output_dir)
            
            # Generate README and guide files
            self._generate_longmemeval_docs(output_dir)
            
            print(f"✅ Generated additional directories:")
            print(f"   - questions_by_type/ ({len(questions_by_type)} types)")
            print(f"   - complete_data_by_type/ ({len(complete_data_by_type)} types)")
            print(f"   - complete_data_by_user/ ({len(users_data)} users)")
            
        except Exception as e:
            print(f"❌ Failed to generate additional files: {e}")
            import traceback
            traceback.print_exc()
    
    def _generate_longmemeval_metadata(self, users_data: dict, question_type_counts: dict, output_dir: Path):
        """Generate metadata.json for LongMemEval-S"""
        
        total_questions = sum(len(data['questions']) for data in users_data.values())
        
        metadata = {
            "dataset_info": {
                "name": "LongMemEval-S",
                "description": "LongMemEval dataset with support for splitting by user and by type",
                "total_users": len(users_data),
                "user_limit": len(users_data),
                "created_at": str(output_dir.absolute())
            },
            "statistics": {
                "total_questions": total_questions,
                "question_types": len(question_type_counts),
                "users": len(users_data)
            },
            "question_types": dict(question_type_counts),
            "users": {user_id.replace('user_', ''): 1 for user_id in users_data.keys()},
            "directories": {
                "questions_by_type": "Questions grouped by type",
                "questions_by_user": "Questions grouped by user", 
                "sessions_by_user": "Sessions grouped by user",
                "complete_data_by_type": "Complete data by type (for evaluation)",
                "complete_data_by_user": "Complete data by user (for evaluation)"
            }
        }
        
        with open(output_dir / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def _generate_longmemeval_docs(self, output_dir: Path):
        """Generate README and guide files"""
        
        readme_content = """# LongMemEval-S Dataset Split

This directory contains the split LongMemEval-S dataset organized for TiMem experiments.

## Directory Structure

- `questions_by_user/` - Questions organized by user ID
- `sessions_by_user/` - Session data organized by user ID  
- `questions_by_type/` - Questions grouped by question type
- `complete_data_by_user/` - Complete data (questions + sessions) per user
- `complete_data_by_type/` - Complete data grouped by question type

## Question Types

1. single-session-user
2. single-session-assistant
3. single-session-preference
4. multi-session
5. knowledge-update
6. temporal-reasoning

## Usage

This split dataset is designed for use with TiMem's memory generation and retrieval experiments.
"""
        
        with open(output_dir / "README.md", 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        guide_content = """# User Isolation Guide

This guide explains how users are isolated in the LongMemEval-S dataset.

## Isolation Strategy

Each user represents a unique conversation scenario with:
- Unique question set
- Unique session history
- Independent memory context

## File Naming

- User files: `user_{question_id}_*.json`
- Question files: `user_{question_id}_questions.json`
- Session files: `user_{question_id}.json`

## Data Integrity

All user data is completely isolated to prevent cross-contamination during experiments.
"""
        
        with open(output_dir / "USER_ISOLATION_GUIDE.md", 'w', encoding='utf-8') as f:
            f.write(guide_content)
    
    def load_users_questions(
        self, 
        num_users: int = None,
        users_per_type: int = 4,
        questions_per_user: int = None,
        use_type_selection: bool = True,
        exclude_incomplete_users: bool = False
    ) -> Dict[str, Dict]:
        """
        Load user question data
        
        Args:
            num_users: Number of users to load (traditional mode, used when use_type_selection=False)
            users_per_type: Number of users to select per question type (used when use_type_selection=True)
            questions_per_user: Limit questions per user (None=all questions)
            use_type_selection: Whether to use type selection strategy (True=select N users from each of 6 types)
            exclude_incomplete_users: Whether to exclude incomplete users (default False=test all 500 users)
        
        Returns:
            {user_id: {
                "user_id": str,
                "question_type": str,
                "questions": [...]
            }}
        """
        print(f"\n{'='*80}")
        print(f"📂 Loading LongMemEval-S question data")
        print(f"{'='*80}")
        print(f"Data directory: {self.questions_dir}")
        
        if not self.questions_dir.exists():
            raise FileNotFoundError(f"Question directory does not exist: {self.questions_dir}")
        
        # Load exclusion list
        exclude_users = set()
        if exclude_incomplete_users:
            exclude_users = self.load_incomplete_users_list()
        
        # Select users
        if use_type_selection:
            # Use type selection strategy: select N users from each of 6 question types
            selected_user_ids, users_by_type = self.select_users_by_question_type(
                self.questions_dir, 
                users_per_type=users_per_type,
                exclude_users=exclude_users
            )
        else:
            # Traditional mode: load first N users (include _abs abstract users, exclude incomplete users)
            question_files = sorted(self.questions_dir.glob("user_*_questions.json"))
            # No longer filter _abs files since abstract questions also need testing
            
            # Apply exclusion logic
            filtered_files = []
            excluded_count = 0
            for f in question_files:
                user_id = f.stem.replace('_questions', '')
                original_id = user_id.replace('user_', '')
                if original_id not in exclude_users:
                    filtered_files.append(f)
                else:
                    excluded_count += 1
            
            # If num_users is None, load all users
            if num_users is None:
                question_files = filtered_files
                if exclude_users:
                    print(f"Found {len(filtered_files)} complete user question files (excluding {excluded_count} incomplete users)")
                else:
                    print(f"Found {len(filtered_files)} user question files")
                print(f"Loading all {len(filtered_files)} users\n")
            else:
                question_files = filtered_files[:num_users]
                if exclude_users:
                    print(f"Found {len(filtered_files)} complete user question files (excluding {excluded_count} incomplete users)")
                else:
                    print(f"Found {len(filtered_files)} user question files")
                print(f"Loading first {len(question_files)} users\n")
            
            selected_user_ids = [f.stem.replace('_questions', '') for f in question_files]
            users_by_type = {}
        
        # Load question data for selected users
        users_data = {}
        
        for user_id in selected_user_ids:
            question_file = self.questions_dir / f"{user_id}_questions.json"
            
            if not question_file.exists():
                print(f"⚠️ Question file does not exist: {question_file.name}")
                continue
            
            try:
                with open(question_file, 'r', encoding='utf-8') as f:
                    questions = json.load(f)
                
                # Question file is an array
                if not isinstance(questions, list):
                    print(f"⚠️ Skip invalid file (not an array): {question_file.name}")
                    continue
                
                if not questions:
                    print(f"⚠️ Skip empty file: {question_file.name}")
                    continue
                
                # Limit question count if specified
                if questions_per_user is not None and questions_per_user > 0:
                    original_count = len(questions)
                    questions = questions[:questions_per_user]
                    print(f"  📊 {user_id}: Limit questions {original_count} → {len(questions)}")
                
                # Get question_type from first question
                question_type = questions[0].get("question_type", "unknown") if questions else "unknown"
                
                users_data[user_id] = {
                    "user_id": user_id,
                    "question_type": question_type,
                    "questions": questions,
                    "file_path": str(question_file)
                }
                
                print(f"✅ {user_id}: {question_type} type, {len(questions)} questions")
                
            except Exception as e:
                print(f"❌ Failed to load {question_file.name}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*80}")
        print(f"📊 Loading completed")
        print(f"{'='*80}")
        print(f"Successfully loaded users: {len(users_data)}")
        total_questions = sum(len(data["questions"]) for data in users_data.values())
        print(f"Total questions: {total_questions}")
        if questions_per_user:
            print(f"Questions per user limit: {questions_per_user}")
        print(f"{'='*80}\n")
        
        return users_data
    
    def load_incomplete_users_list(self) -> Set[str]:
        """Load incomplete users list"""
        incomplete_users = set()
        try:
            incomplete_file = self.data_dir / "incomplete_users.txt"
            if incomplete_file.exists():
                with open(incomplete_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        user_id = line.strip()
                        if user_id:
                            incomplete_users.add(user_id)
                print(f"📋 Loaded {len(incomplete_users)} incomplete user IDs")
            else:
                print("⚠️ Incomplete users list file does not exist, will test all users")
        except Exception as e:
            print(f"⚠️ Failed to load incomplete users list: {e}")
        
        return incomplete_users
    
    def select_users_by_question_type(
        self, 
        questions_dir: Path, 
        users_per_type: int = 4,
        exclude_users: Set[str] = None
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """
        Select users by question type
        
        Args:
            questions_dir: Questions directory
            users_per_type: Number of users to select per type
            exclude_users: Set of user IDs to exclude
        
        Returns:
            (selected_user_ids, users_by_type)
        """
        exclude_users = exclude_users or set()
        
        # Group users by question type
        users_by_type = {
            "factual": [],
            "inferential": [],
            "counterfactual": [],
            "metacognitive": [],
            "emotional": [],
            "comparative": [],
            "unknown": []
        }
        
        # Scan all question files
        for question_file in questions_dir.glob("user_*_questions.json"):
            try:
                user_id = question_file.stem.replace('_questions', '')
                original_id = user_id.replace('user_', '')
                
                # Skip users in exclusion list
                if original_id in exclude_users:
                    continue
                
                with open(question_file, 'r', encoding='utf-8') as f:
                    questions = json.load(f)
                
                if not questions or not isinstance(questions, list):
                    continue
                
                # Get question type
                question_type = questions[0].get("question_type", "unknown")
                
                # Add to corresponding type group
                if question_type in users_by_type:
                    users_by_type[question_type].append(user_id)
                else:
                    users_by_type["unknown"].append(user_id)
                    
            except Exception:
                continue
        
        # Print user count by question type
        print("\n📊 User statistics by question type:")
        for qtype, users in users_by_type.items():
            print(f"  - {qtype}: {len(users)} users")
        
        # Select specified number of users from each type
        selected_user_ids = []
        print(f"\n🎯 Selecting {users_per_type} users per type:")
        
        for qtype, users in users_by_type.items():
            if qtype == "unknown":
                continue
                
            # Sort to ensure consistent results
            sorted_users = sorted(users)
            selected = sorted_users[:users_per_type]
            
            print(f"  - {qtype}: Selected {len(selected)}/{len(users)} users")
            selected_user_ids.extend(selected)
        
        # Remove duplicates and sort
        selected_user_ids = sorted(set(selected_user_ids))
        print(f"\n✅ Total selected: {len(selected_user_ids)} users")
        
        return selected_user_ids, users_by_type
    
    def load_question_types(self) -> Dict[tuple, str]:
        """
        Load question type mapping from question files
        Returns dictionary of {(user_id, question_idx): question_type}
        """
        question_types_map = {}
        
        if not self.questions_dir.exists():
            print(f"⚠️ Warning: Question directory does not exist: {self.questions_dir}")
            return question_types_map
        
        try:
            for json_file in self.questions_dir.glob("user_*_questions.json"):
                # Extract user_id from filename
                filename = json_file.stem  # e.g., "user_001be529_questions"
                parts = filename.split('_')
                if len(parts) >= 2:
                    user_id = f"user_{parts[1]}"
                    if len(parts) > 2 and parts[2] != "questions":
                        # Handle user_xxx_abs_questions case
                        user_id = f"user_{parts[1]}_{parts[2]}"
                else:
                    continue
                
                # Read question file
                with open(json_file, 'r', encoding='utf-8') as f:
                    questions_data = json.load(f)
                
                # questions_data is a list
                for question_item in questions_data:
                    if isinstance(question_item, dict):
                        question_idx = question_item.get("question_index", 1)
                        question_type = question_item.get("question_type", "unknown")
                        question_types_map[(user_id, question_idx)] = question_type
        except Exception as e:
            print(f"⚠️ Error loading question types: {e}")
        
        return question_types_map
