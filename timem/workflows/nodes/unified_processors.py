"""
Unified Memory Processor

Integrates new L1Processor and legacy L2-L5MemoryProcessor
Ensures architectural consistency and compatibility
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, time, date
import logging
import traceback
import uuid
import re
import asyncio

from timem.workflows.state import MemoryState
from timem.utils.time_manager import get_time_manager, TimeManager
from timem.models.memory import create_memory_by_level, MemoryLevel, FragmentMemory, SessionMemory
from timem.utils.logging import get_logger
from timem.memory.memory_generator import MemoryGenerator
from timem.utils.time_parser import time_parser
from timem.utils.time_utils import ensure_iso_string
from timem.workflows.nodes.memory_processors.base_processor import BaseMemoryProcessor
from llm.llm_manager import get_llm

logger = get_logger(__name__)


# ============================================================================
# Helper functions (reused from multi_layer_memory_generator.py)
# ============================================================================

def _get_memory_ids(memories: List[Any]) -> List[str]:
    """Safely extract IDs from memory objects or dictionary list"""
    if not memories:
        return []
    ids = []
    for mem in memories:
        mem_id = None
        if isinstance(mem, dict):
            mem_id = mem.get("id")
        else:
            mem_id = getattr(mem, "id", None)
        
        if mem_id:
            ids.append(mem_id)
    return ids


def _validate_memory_level(memory: Any, expected_level: str) -> bool:
    """Validate if memory level is correct"""
    if isinstance(memory, dict):
        memory_level = memory.get("level")
    else:
        memory_level = getattr(memory, "level", None)

    # Compatible with MemoryLevel enum
    if isinstance(memory_level, MemoryLevel):
        memory_level = memory_level.value
    
    return memory_level == expected_level


def _filter_memories_by_level(memories: List[Any], expected_level: str) -> List[Any]:
    """Filter memory list by level"""
    logger.info(f"🔍 [MemoryGenerator] Starting memory level filtering: expected={expected_level}, input count={len(memories)}")
    
    valid_memories = []
    for memory in memories:
        memory_level = memory.get('level') if isinstance(memory, dict) else getattr(memory, 'level', None)
        if isinstance(memory_level, MemoryLevel):
            memory_level = memory_level.value
        logger.info(f"🔍 [MemoryGenerator] Checking memory level: expected={expected_level}, actual={memory_level}")
        
        if memory_level == expected_level:
            valid_memories.append(memory)
            logger.info(f"✅ [MemoryGenerator] Memory level matched: {memory_level}")
        else:
            logger.warning(f"❌ [MemoryGenerator] Skipping mismatched memory level: {memory_level} != {expected_level}")
    
    logger.info(f"✅ [MemoryGenerator] Level filtering completed: input={len(memories)}, output={len(valid_memories)}")
    return valid_memories


# ============================================================================
# New L1Processor (reused from memory_processors/l1_processor.py)
# ============================================================================

class L1Processor(BaseMemoryProcessor):
    """L1 fragment-level memory processor, responsible for generating session fragment memories
    
    Uses new interface: process(state: MemoryState) -> MemoryState
    """
    
    @property
    def memory_level(self) -> str:
        """Return memory level"""
        return "L1"
    
    @property
    def child_level(self) -> str:
        """L1 has no child memories"""
        return ""
    
    def __init__(self):
        """Initialize L1 processor"""
        super().__init__()
        self.time_parser = time_parser
        # Ensure llm instance exists
        if not hasattr(self, 'llm'):
            self.llm = get_llm()
        
        # Ensure memory_indexer is initialized
        if not hasattr(self, 'memory_indexer') or self.memory_indexer is None:
            from timem.workflows.nodes.memory_indexer import get_memory_indexer
            self.memory_indexer = get_memory_indexer()
        
        logger.info("L1 fragment-level memory processor initialized")
    
    async def process(self, state: MemoryState) -> MemoryState:
        """Process L1 fragment-level memory generation"""
        logger.info("Executing L1 memory processing")
        print(f"\n📝 Executing L1 memory processing - Session ID: {state.get('session_id', 'unknown')}")

        try:
            # Get necessary information
            content = state.get("content", "")
            session_id = state.get("session_id", "")
            user_id = state.get("user_id", "")
            expert_id = state.get("expert_id", "")
            
            # Prioritize historical memories passed by HistoryCollector
            historical_memory_ids = state.get("L1_historical_memory_ids", [])
            if not historical_memory_ids:
                # Fallback to memory_indexer, use global config historical memory limit
                historical_memory_ids = await self.memory_indexer.get_historical_memories(
                    state=state,
                    layer=self.memory_level
                )
                print(f"  📚 Retrieved historical memories using memory_indexer: {len(historical_memory_ids)} items")
            else:
                print(f"  📚 Using historical memories passed by HistoryCollector: {len(historical_memory_ids)} items")
                
            # If historical_memory_ids is a list of memory objects, extract IDs
            if historical_memory_ids and hasattr(historical_memory_ids[0], 'id'):
                historical_memory_ids = [getattr(m, 'id', 'unknown') for m in historical_memory_ids if hasattr(m, 'id')]
                print(f"  📋 Extracted IDs from memory objects: {historical_memory_ids}")
                
            # If no content, cannot generate memory
            if not content:
                logger.warning("No content, cannot generate L1 memory")
                state["error"] = "No content, cannot generate L1 memory"
                return state
                
            # Get timestamp
            timestamp = self._get_timestamp(state)
            
            # Generate L1 memory content
            memory_content = await self._generate_l1_content(content, historical_memory_ids)
            
            # Parse dialogue turns
            dialogue_turns = self._parse_dialogue(content)
            
            # Generate memory object
            memory_id = str(uuid.uuid4())
            memory = {
                "id": memory_id,
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "level": "L1",
                "title": f"Fragment Memory - {timestamp}",
                "content": memory_content,
                "original_text": content,
                "dialogue_turns": dialogue_turns,
                "created_at": timestamp,
                "updated_at": timestamp,
                "historical_memory_ids": historical_memory_ids,
                "child_memory_ids": [],
            }
            
            # Convert to memory object
            memory_obj = self.dict_to_memory_object(memory)
            
            # Ensure memory object contains complete historical memory index
            if hasattr(memory_obj, '__dict__'):
                setattr(memory_obj, 'historical_memory_ids', historical_memory_ids)
                setattr(memory_obj, 'child_memory_ids', [])
            elif isinstance(memory_obj, dict):
                memory_obj["historical_memory_ids"] = historical_memory_ids
                memory_obj["child_memory_ids"] = []
            
            # Update state
            state["generated_memory"] = memory_obj
            
            logger.info(f"Successfully generated L1 memory: {memory_id}")
            print(f"  ✓ Successfully generated L1 memory: {memory_id}")
            print(f"  📋 Historical memory index: {len(historical_memory_ids)} items")
            
            return state
            
        except Exception as e:
            error_msg = f"L1 memory generation failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            print(f"  ❌ {error_msg}")
            state["error"] = error_msg
            return state
    
    async def _generate_l1_content(self, content: str, historical_memory_ids: List[str]) -> str:
        """Generate L1 memory content"""
        try:
            # Parse dialogue turns
            dialogue_turns = self._parse_dialogue(content)
            
            # If no dialogue turns extracted, try using entire content as single turn
            if not dialogue_turns:
                dialogue_turns = [{"speaker": "unknown", "content": content}]
            
            print(f"📝 Parsed {len(dialogue_turns)} dialogue turns")
            print(f"🔍 Parsing dialogue turns: {len(dialogue_turns)} turns")
            for i, turn in enumerate(dialogue_turns):
                print(f"  {i+1}. {turn['speaker']}: {turn['content'][:50]}...")
            
            # Get historical memory content
            hist_with_time = []
            if historical_memory_ids:
                print(f"📚 Retrieving historical memory content, count: {len(historical_memory_ids)}")
                try:
                    if not hasattr(self, 'memory_indexer') or self.memory_indexer is None:
                        from timem.workflows.nodes.memory_indexer import get_memory_indexer
                        self.memory_indexer = get_memory_indexer()
                    
                    memories = await self.memory_indexer.batch_get_memories_by_ids(historical_memory_ids)
                    for m in memories:
                        if isinstance(m, dict):
                            c = m.get("content", "")
                            t = m.get("created_at")
                        else:
                            c = getattr(m, "content", "")
                            t = getattr(m, "created_at", None)
                        hist_with_time.append({"created_at": str(t or ""), "content": c})
                    
                    # Sort by time ascending (from far to near)
                    hist_with_time = sorted(hist_with_time, key=lambda x: str(x.get("created_at") or ""))
                    print(f"📚 Retrieved {len(hist_with_time)} historical contents")
                except Exception as e:
                    logger.warning(f"Failed to retrieve historical memory content: {e}")
                    print(f"⚠️ Failed to retrieve historical memory content: {e}")
            else:
                print(f"📚 No historical memory IDs")

            previous_text = "\n".join([
                (f"[{h['created_at']}] {h['content']}" if h.get("created_at") else h.get("content", ""))
                for h in hist_with_time
                if (h.get("content") or "").strip()
            ])

            return await self._generate_content(
                content=content,
                dialogue_turns=dialogue_turns,
                historical_contents=[previous_text] if previous_text else []
            )
            
        except Exception as e:
            logger.error(f"Error generating L1 content: {e}", exc_info=True)
            # Return simple fallback content
            speakers = set(turn["speaker"] for turn in dialogue_turns if turn["speaker"] != "unknown")
            speakers_str = ", ".join(speakers) if speakers else "Unknown speaker"
            return f"Dialogue fragment of {speakers_str}: {content[:50]}{'...' if len(content) > 50 else ''}"

    def _parse_dialogue(self, text: str) -> List[Dict[str, str]]:
        """Parse dialogue text, extract speakers and content"""
        result = []
        if not text:
            return result
            
        lines = text.strip().split('\n')
        current_turn = None
        
        for line in lines:
            if not line.strip():
                continue
            
            match = re.match(r'^(User|Assistant|Expert)[:：-]\s*(.*)', line, re.IGNORECASE)
            
            if match:
                if current_turn is not None:
                    result.append(current_turn)
                
                speaker = match.group(1).strip()
                content = match.group(2).strip()
                current_turn = {"speaker": speaker, "content": content}
            else:
                if current_turn is not None:
                    current_turn["content"] += "\n" + line
                else:
                    if not result:
                        current_turn = {"speaker": "Assistant", "content": text.strip()}
                        break
                    else:
                        if result:
                            result[-1]["content"] += "\n" + line
        
        if current_turn is not None:
            result.append(current_turn)
                
        return result
        
    async def _generate_content(self, content: str, dialogue_turns: List[Dict[str, str]], 
                               historical_contents: List[str] = None) -> str:
        """Generate content for L1 memory"""
        try:
            if historical_contents:
                content_result = await self.memory_generator.generate_l1_content(
                    new_dialogue=content,
                    previous_content=historical_contents[0] if historical_contents else None
                )
                return content_result
            else:
                content_result = await self.memory_generator.generate_l1_content(content)
                return content_result
                
        except Exception as e:
            logger.error(f"Error generating L1 content: {e}", exc_info=True)
            speakers = set(turn["speaker"] for turn in dialogue_turns if turn["speaker"] != "unknown")
            speakers_str = ", ".join(speakers) if speakers else "Unknown speaker"
            return f"Dialogue fragment of {speakers_str}: {content[:50]}{'...' if len(content) > 50 else ''}"

    def _get_timestamp(self, state: MemoryState) -> str:
        """Get timestamp from state"""
        if state.get("original_timestamp"):
            return ensure_iso_string(state["original_timestamp"])
        
        if state.get("timestamp"):
            return ensure_iso_string(state["timestamp"])
        
        return ensure_iso_string(datetime.now())
    
    def dict_to_memory_object(self, memory_dict: Dict[str, Any]) -> Any:
        """Convert dictionary to memory object"""
        try:
            from timem.utils.memory_object_utils import convert_dict_to_memory
            memory = convert_dict_to_memory(memory_dict, "L1")
            
            logger.debug(f"L1 memory conversion completed: {memory_dict.get('id', 'unknown')}")
            return memory
            
        except Exception as e:
            logger.error(f"Error converting L1 memory dictionary: {str(e)}", exc_info=True)
            return memory_dict


# ============================================================================
# Legacy L2-L5MemoryProcessor base class and implementation (reused from multi_layer_memory_generator.py)
# ============================================================================

class MemoryProcessor:
    """
    Memory processor base class, defines common memory processing interface (legacy)
    
    Uses legacy interface: process(state, user_id, expert_id, layer, child_memories, historical_memories)
    """
    
    def __init__(self, time_manager=None):
        self.time_manager = time_manager or get_time_manager()
    
    async def process(self, state: MemoryState, user_id: str, expert_id: str, layer: str, 
                     child_memories: List[Dict[str, Any]], historical_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses must implement this method")


class L2MemoryProcessor(MemoryProcessor):
    """L2 memory processor"""
    
    def __init__(self, time_manager=None):
        super().__init__(time_manager=time_manager)
        self.memory_generator = MemoryGenerator()
        logger.info(f"🔍 [L2Processor] MemoryGenerator initialized successfully")
        
        # Ensure prompt configuration is loaded correctly
        self._ensure_prompts_loaded()
    
    def _ensure_prompts_loaded(self):
        """Ensure prompt configuration is loaded correctly, retry if failed"""
        try:
            # Check if L2 prompt is available
            l2_prompt = self.memory_generator.prompt_manager.get_prompt("l2_session_summary")
            if not l2_prompt:
                logger.warning("L2 prompt not available, attempting to reload prompt configuration...")
                from timem.utils.prompt_manager import reload_prompt_manager
                reload_prompt_manager()
                # Recreate MemoryGenerator instance
                self.memory_generator = MemoryGenerator()
                logger.info("✅ L2Processor prompt configuration reloaded successfully")
        except Exception as e:
            logger.error(f"L2Processor prompt configuration check failed: {e}")
    
    async def process(self, state: MemoryState, user_id: str, expert_id: str, layer: str, 
                     child_memories: List[Dict[str, Any]], historical_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process L2 session-level memory generation"""
        decision = state.get("memory_decisions", {}).get(layer, {})
        collection_info = decision.get("collection_info", {}) if isinstance(decision, dict) else {}
        target_session_id = collection_info.get("target_session_id")
        current_session_id = state.get("session_id", "")
        
        session_id = target_session_id if target_session_id else current_session_id
        timestamp = state.get("timestamp", "")
        
        logger.info(f"🔍 [L2Processor] ========== Starting L2 memory processing ==========")
        logger.info(f"🔍 [L2Processor] Using session ID: {session_id}")
        logger.info(f"🔍 [L2Processor] Input child memories count: {len(child_memories)}")
        
        valid_child_memories = _filter_memories_by_level(child_memories, "L1")
        valid_historical_memories = _filter_memories_by_level(historical_memories, "L2")
        
        session_time = state.get("timestamp")
        if isinstance(session_time, str):
            session_time = self.time_manager.parse_iso_time(session_time)
        if session_time and getattr(session_time, 'tzinfo', None) is not None:
            session_time = session_time.replace(tzinfo=None)
        
        # Infer actual time range of session from L1 child memories
        if valid_child_memories:
            child_times = []
            for mem in valid_child_memories:
                mem_time = mem.get('created_at') if isinstance(mem, dict) else getattr(mem, 'created_at', None)
                if mem_time:
                    if isinstance(mem_time, str):
                        mem_time = self.time_manager.parse_iso_time(mem_time)
                    if mem_time and getattr(mem_time, 'tzinfo', None) is not None:
                        mem_time = mem_time.replace(tzinfo=None)
                    if mem_time:
                        child_times.append(mem_time)
            
            if child_times:
                time_window_start = min(child_times)
                time_window_end = max(child_times)
            else:
                time_window_start = session_time or self.time_manager.get_current_time()
                time_window_end = session_time or time_window_start
        else:
            time_window_start = session_time or self.time_manager.get_current_time()
            time_window_end = session_time or time_window_start
        
        created_ts = session_time or time_window_end
        
        # Generate content for L2
        try:
            from timem.workflows.nodes.memory_time_sorter import MemoryTimeSorter
            time_sorter = MemoryTimeSorter()
            
            sorted_child_memories = time_sorter.sort_child_memories(valid_child_memories, sort_order="asc")
            
            child_contents = []
            for mem in sorted_child_memories:
                child_contents.append(mem.get('content') if isinstance(mem, dict) else getattr(mem, 'content', ''))
            
            previous_content = None
            if valid_historical_memories:
                sorted_historical_memories = time_sorter.sort_historical_memories(
                    valid_historical_memories, limit=3, sort_order="desc"
                )
                
                previous_content = time_sorter.format_memories_for_prompt(
                    sorted_historical_memories, memory_type="historical"
                )
            
            generated_l2 = await self.memory_generator.generate_l2_content(child_contents, previous_content)
            logger.info(f"✅ [L2Processor] LLM generated L2 content successfully, length: {len(generated_l2)} characters")
            
        except Exception as e:
            logger.error(f"❌ [L2Processor] L2 content generation failed: {e}", exc_info=True)
            generated_l2 = f"Session summary - Summary of dialogue content for {session_id}"

        memory_params = {
            "level": MemoryLevel.L2,
            "user_id": user_id,
            "expert_id": expert_id,
            "session_id": session_id,
            "title": f"Session Memory - {session_id}",
            "content": generated_l2 or f"Session summary - Summary of dialogue content for {session_id}",
            "time_window_start": time_window_start,
            "time_window_end": time_window_end,
            "created_at": created_ts,
            "updated_at": created_ts,
            "child_memory_ids": _get_memory_ids(valid_child_memories),
            "historical_memory_ids": _get_memory_ids(valid_historical_memories)
        }

        memory = create_memory_by_level(**memory_params)
        logger.info(f"✅ [L2Processor] L2 memory generated successfully: {memory.id}")
        logger.info(f"🔍 [L2Processor] ========== L2 memory processing completed ==========")
        
        return memory


class L3MemoryProcessor(MemoryProcessor):
    """L3 memory processor"""
    
    def __init__(self, time_manager=None):
        super().__init__(time_manager=time_manager)
        self.memory_generator = MemoryGenerator()
        self._ensure_prompts_loaded()
    
    def _ensure_prompts_loaded(self):
        """Ensure prompt configuration is loaded correctly"""
        try:
            l3_prompt = self.memory_generator.prompt_manager.get_prompt("l3_daily_summary")
            if not l3_prompt:
                logger.warning("L3 prompt not available, attempting to reload...")
                from timem.utils.prompt_manager import reload_prompt_manager
                reload_prompt_manager()
                self.memory_generator = MemoryGenerator()
        except Exception as e:
            logger.error(f"L3Processor prompt configuration check failed: {e}")
    
    async def process(self, state: MemoryState, user_id: str, expert_id: str, layer: str, 
                     child_memories: List[Dict[str, Any]], historical_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        timestamp = state.get("original_timestamp", state["timestamp"])
        decision = state["memory_decisions"].get(layer, {})
        collection_info = decision.get("collection_info", {})
        time_window = collection_info.get("time_window", {})
        
        start_time = None
        date_str = ""
        if time_window and "start_time" in time_window:
            start_time_val = time_window["start_time"]
            if isinstance(start_time_val, str):
                start_time = self.time_manager.parse_iso_time(start_time_val)
            else:
                start_time = start_time_val
            date_str = start_time.strftime("%Y-%m-%d")
        else:
            start_time = timestamp
            date_str = timestamp.strftime("%Y-%m-%d")

        logger.info(f"🔍 [L3Processor] Starting L3 memory processing: date_str={date_str}")

        title = f"Daily Report - {date_str}"
        
        valid_child_memories = _filter_memories_by_level(child_memories, "L2")
        
        content = None
        generated_l3 = None
        
        try:
            if not valid_child_memories:
                error_msg = (f"L3 generation failed: No valid L2 child memories (date_str={date_str}, "
                            f"user_id={user_id}, expert_id={expert_id})")
                logger.error(f"❌ [L3Processor] {error_msg}")
                raise ValueError(error_msg)
            else:
                from timem.workflows.nodes.memory_time_sorter import MemoryTimeSorter
                time_sorter = MemoryTimeSorter()
                
                sorted_child_memories = time_sorter.sort_child_memories(valid_child_memories, sort_order="asc")
                
                child_contents = []
                for mem in sorted_child_memories:
                    child_content = mem.content if hasattr(mem, 'content') else mem.get('content', '')
                    child_contents.append(child_content)
                
                previous_content = None
                valid_historical_memories = _filter_memories_by_level(historical_memories, "L3")
                if valid_historical_memories:
                    sorted_historical_memories = time_sorter.sort_historical_memories(
                        valid_historical_memories, limit=3, sort_order="desc"
                    )
                    
                    previous_content = time_sorter.format_memories_for_prompt(
                        sorted_historical_memories, memory_type="historical"
                    )
                
                content = await self.memory_generator.generate_l3_content(child_contents, previous_content, date_str)
                logger.info(f"✅ [L3Processor] LLM generated L3 content successfully, length: {len(content)} characters")
                generated_l3 = content
        except Exception as e:
            logger.error(f"❌ [L3Processor] L3 content generation failed: {e}", exc_info=True)
            raise
        
        child_ids = _get_memory_ids(valid_child_memories)
        
        valid_historical_memories = _filter_memories_by_level(historical_memories, "L3")
        historical_ids = _get_memory_ids(valid_historical_memories)

        final_created = None
        if time_window:
            end_time_val = time_window.get("end_time")
            if isinstance(end_time_val, str):
                final_created = self.time_manager.parse_iso_time(end_time_val)
            elif isinstance(end_time_val, datetime):
                final_created = end_time_val
        final_created = final_created or timestamp

        memory_params = {
            "level": MemoryLevel.L3,
            "user_id": user_id,
            "expert_id": expert_id,
            "title": title,
            "content": content,
            "created_at": final_created if isinstance(final_created, datetime) else self.time_manager.get_current_time(),
            "updated_at": final_created if isinstance(final_created, datetime) else self.time_manager.get_current_time(),
            "date_value": start_time.date() if start_time else timestamp.date(),
            "child_memory_ids": child_ids,
            "historical_memory_ids": historical_ids,
        }

        if time_window:
            if "start_time" in time_window:
                memory_params["time_window_start"] = time_window["start_time"]
            if "end_time" in time_window:
                memory_params["time_window_end"] = time_window["end_time"]

        memory = create_memory_by_level(**memory_params)
        
        logger.info(f"✅ [L3Processor] L3 memory generation completed: id={memory.id}")
        return memory


class L4MemoryProcessor(MemoryProcessor):
    """L4 memory processor"""
    
    def __init__(self, time_manager=None):
        super().__init__(time_manager=time_manager)
        self.memory_generator = MemoryGenerator()
        self._ensure_prompts_loaded()
    
    def _ensure_prompts_loaded(self):
        """Ensure prompt configuration is loaded correctly"""
        try:
            l4_prompt = self.memory_generator.prompt_manager.get_prompt("l4_weekly_summary")
            if not l4_prompt:
                logger.warning("L4 prompt not available, attempting to reload...")
                from timem.utils.prompt_manager import reload_prompt_manager
                reload_prompt_manager()
                self.memory_generator = MemoryGenerator()
        except Exception as e:
            logger.error(f"L4Processor prompt configuration check failed: {e}")
    
    async def process(self, state: MemoryState, user_id: str, expert_id: str, layer: str, 
                     child_memories: List[Dict[str, Any]], historical_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        timestamp = state.get("original_timestamp", state["timestamp"])
        decision = state["memory_decisions"].get(layer, {})
        collection_info = decision.get("collection_info", {})
        time_window = collection_info.get("time_window", {})
        
        week_start_str, week_end_str, start_time_obj = "", "", None
        if time_window:
            start_time, end_time = time_window.get("start_time"), time_window.get("end_time")
            if isinstance(start_time, str): start_time_obj = self.time_manager.parse_iso_time(start_time)
            elif isinstance(start_time, datetime): start_time_obj = start_time
            if start_time_obj: week_start_str = start_time_obj.strftime("%Y-%m-%d")

            end_time_obj = None
            if isinstance(end_time, str): 
                end_time_obj = self.time_manager.parse_iso_time(end_time)
            elif isinstance(end_time, datetime): 
                end_time_obj = end_time
            elif isinstance(end_time, date): 
                end_time_obj = datetime.combine(end_time, datetime.max.time())
            if end_time_obj: 
                week_end_str = end_time_obj.strftime("%Y-%m-%d")

        logger.info(f"🔍 [L4Processor] Starting L4 memory processing: week_start_str={week_start_str}, week_end_str={week_end_str}")

        title = f"Weekly Report - {week_start_str} to {week_end_str}"
        
        valid_child_memories = _filter_memories_by_level(child_memories, "L3")
        
        content = None
        generated_l4 = None
        
        try:
            if not valid_child_memories:
                error_msg = (f"L4 generation failed: No valid L3 child memories (week_start_str={week_start_str}, "
                            f"user_id={user_id}, expert_id={expert_id})")
                logger.error(f"❌ [L4Processor] {error_msg}")
                raise ValueError(error_msg)
            else:
                from timem.workflows.nodes.memory_time_sorter import MemoryTimeSorter
                time_sorter = MemoryTimeSorter()
                
                sorted_child_memories = time_sorter.sort_child_memories(valid_child_memories, sort_order="asc")
                
                child_contents = []
                for mem in sorted_child_memories:
                    child_content = mem.content if hasattr(mem, 'content') else mem.get('content', '')
                    child_contents.append(child_content)
                
                previous_content = None
                valid_historical_memories = _filter_memories_by_level(historical_memories, "L4")
                if valid_historical_memories:
                    sorted_historical_memories = time_sorter.sort_historical_memories(
                        valid_historical_memories, limit=3, sort_order="desc"
                    )
                    
                    previous_content = time_sorter.format_memories_for_prompt(
                        sorted_historical_memories, memory_type="historical"
                    )
                
                # Calculate year and week_number (if start_time_obj available)
                year_val, week_number_val = (start_time_obj.isocalendar()[0], start_time_obj.isocalendar()[1]) if start_time_obj else (timestamp.isocalendar()[0], timestamp.isocalendar()[1])
                content = await self.memory_generator.generate_l4_content(
                    child_contents, previous_content, 
                    year=year_val, week_number=week_number_val,
                    week_start=week_start_str, week_end=week_end_str
                )
                logger.info(f"✅ [L4Processor] LLM generated L4 content successfully, length: {len(content)} characters")
                generated_l4 = content
        except Exception as e:
            logger.error(f"❌ [L4Processor] L4 content generation failed: {e}", exc_info=True)
            raise
        
        child_ids = _get_memory_ids(valid_child_memories)
        
        valid_historical_memories = _filter_memories_by_level(historical_memories, "L4")
        historical_ids = _get_memory_ids(valid_historical_memories)
        
        year, week_number = (start_time_obj.isocalendar()[0], start_time_obj.isocalendar()[1]) if start_time_obj else (timestamp.isocalendar()[0], timestamp.isocalendar()[1])

        final_created = None
        if time_window:
            end_time_val = time_window.get("end_time")
            if isinstance(end_time_val, str):
                final_created = self.time_manager.parse_iso_time(end_time_val)
            elif isinstance(end_time_val, datetime):
                final_created = end_time_val
        final_created = final_created or timestamp

        memory_params = {
            "level": MemoryLevel.L4,
            "user_id": user_id,
            "expert_id": expert_id,
            "title": title,
            "content": content,
            "created_at": final_created if isinstance(final_created, datetime) else self.time_manager.get_current_time(),
            "updated_at": final_created if isinstance(final_created, datetime) else self.time_manager.get_current_time(),
            "year": year,
            "week_number": week_number,
            "child_memory_ids": child_ids,
            "historical_memory_ids": historical_ids,
        }
        
        if time_window:
            if "start_time" in time_window:
                memory_params["time_window_start"] = time_window["start_time"]
            if "end_time" in time_window:
                memory_params["time_window_end"] = time_window["end_time"]

        memory = create_memory_by_level(**memory_params)
        
        logger.info(f"✅ [L4Processor] L4 memory generation completed: id={memory.id}")
        return memory


class L5MemoryProcessor(MemoryProcessor):
    """L5 memory processor"""
    
    def __init__(self, time_manager=None):
        super().__init__(time_manager=time_manager)
        self.memory_generator = MemoryGenerator()
        self._ensure_prompts_loaded()
    
    def _ensure_prompts_loaded(self):
        """Ensure prompt configuration is loaded correctly"""
        try:
            l5_prompt = self.memory_generator.prompt_manager.get_prompt("l5_high_level_summary")
            if not l5_prompt:
                logger.warning("L5 prompt not available, attempting to reload...")
                from timem.utils.prompt_manager import reload_prompt_manager
                reload_prompt_manager()
                self.memory_generator = MemoryGenerator()
        except Exception as e:
            logger.error(f"L5Processor prompt configuration check failed: {e}")
    
    async def process(self, state: MemoryState, user_id: str, expert_id: str, layer: str, 
                     child_memories: List[Dict[str, Any]], historical_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        timestamp = state.get("original_timestamp", state["timestamp"])
        decision = state["memory_decisions"].get(layer, {})
        collection_info = decision.get("collection_info", {})
        time_window = collection_info.get("time_window", {})
        
        month_start_str, month_end_str, start_time_obj = "", "", None
        if time_window:
            start_time, end_time = time_window.get("start_time"), time_window.get("end_time")
            if isinstance(start_time, str): start_time_obj = self.time_manager.parse_iso_time(start_time)
            elif isinstance(start_time, datetime): start_time_obj = start_time
            if start_time_obj: month_start_str = start_time_obj.strftime("%Y-%m")

            end_time_obj = None
            if isinstance(end_time, str): 
                end_time_obj = self.time_manager.parse_iso_time(end_time)
            elif isinstance(end_time, datetime): 
                end_time_obj = end_time
            elif isinstance(end_time, date): 
                end_time_obj = datetime.combine(end_time, datetime.max.time())
            if end_time_obj: 
                month_end_str = end_time_obj.strftime("%Y-%m")

        logger.info(f"🔍 [L5Processor] Starting to process L5 memory: month_start_str={month_start_str}")

        title = f"Monthly Report - {month_start_str}"
        
        valid_child_memories = _filter_memories_by_level(child_memories, "L4")
        
        content = None
        generated_l5 = None
        
        try:
            if not valid_child_memories:
                logger.warning(f"⚠️ [L5Processor] No valid L4 child memories, attempting fallback to L3 memories")
                
                try:
                    from timem.workflows.nodes.memory_indexer import UnifiedMemoryIndexer
                    memory_indexer = UnifiedMemoryIndexer()
                    
                    if time_window and start_time_obj:
                        month_start = start_time_obj.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        if start_time_obj.month == 12:
                            month_end = start_time_obj.replace(year=start_time_obj.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                        else:
                            month_end = start_time_obj.replace(month=start_time_obj.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
                        
                        l3_memories = await memory_indexer.get_memories_by_time_window(
                            user_id, expert_id, "L3", month_start, month_end, 50
                        )
                        
                        if l3_memories:
                            logger.info(f"✅ [L5Processor] Fallback mechanism successful: found {len(l3_memories)} L3 memories")
                            
                            from timem.workflows.nodes.memory_time_sorter import MemoryTimeSorter
                            time_sorter = MemoryTimeSorter()
                            
                            sorted_l3_memories = time_sorter.sort_child_memories(l3_memories, sort_order="asc")
                            
                            l3_contents = []
                            for mem in sorted_l3_memories:
                                l3_content = mem.content if hasattr(mem, 'content') else mem.get('content', '')
                                l3_contents.append(l3_content)
                            
                            # Calculate month time parameters
                            year_val = start_time_obj.year
                            month_val = start_time_obj.month
                            month_start_date = month_start.strftime("%Y-%m-%d")
                            month_end_date = month_end.strftime("%Y-%m-%d")
                            
                            content = await self.memory_generator.generate_l5_content(
                                l3_contents, None,
                                year=year_val, month=month_val,
                                month_start=month_start_date, month_end=month_end_date
                            )
                            generated_l5 = content
                            logger.info(f"✅ [L5Processor] Successfully generated L5 content based on L3 memories, length: {len(content)} characters")
                        else:
                            error_msg = (f"L5 generation failed: neither L4 child memories nor L3 memories available as fallback "
                                        f"(month_start_str={month_start_str}, user_id={user_id}, expert_id={expert_id})")
                            logger.error(f"❌ [L5Processor] {error_msg}")
                            raise ValueError(error_msg)
                    else:
                        error_msg = (f"L5 generation failed: unable to get time window information "
                                    f"(month_start_str={month_start_str}, user_id={user_id}, expert_id={expert_id})")
                        logger.error(f"❌ [L5Processor] {error_msg}")
                        raise ValueError(error_msg)
                        
                except Exception as fallback_error:
                    logger.error(f"❌ [L5Processor] Fallback mechanism failed: {fallback_error}")
                    if isinstance(fallback_error, ValueError):
                        raise
                    else:
                        error_msg = (f"L5 generation failed: fallback mechanism exception (month_start_str={month_start_str}, "
                                    f"user_id={user_id}, expert_id={expert_id}, error={fallback_error})")
                        raise ValueError(error_msg) from fallback_error
            else:
                from timem.workflows.nodes.memory_time_sorter import MemoryTimeSorter
                time_sorter = MemoryTimeSorter()
                
                sorted_child_memories = time_sorter.sort_child_memories(valid_child_memories, sort_order="asc")
                
                child_contents = []
                for mem in sorted_child_memories:
                    child_content = mem.content if hasattr(mem, 'content') else mem.get('content', '')
                    child_contents.append(child_content)
                
                previous_content = None
                valid_historical_memories = _filter_memories_by_level(historical_memories, "L5")
                if valid_historical_memories:
                    sorted_historical_memories = time_sorter.sort_historical_memories(
                        valid_historical_memories, limit=3, sort_order="desc"
                    )
                    
                    previous_content = time_sorter.format_memories_for_prompt(
                        sorted_historical_memories, memory_type="historical"
                    )
                
                # Calculate month time parameters
                year_val = start_time_obj.year if start_time_obj else timestamp.year
                month_val = start_time_obj.month if start_time_obj else timestamp.month
                # Calculate month start and end dates
                import calendar
                from datetime import datetime as dt
                first_day = dt(year_val, month_val, 1)
                last_day_num = calendar.monthrange(year_val, month_val)[1]
                last_day = dt(year_val, month_val, last_day_num)
                month_start_date = first_day.strftime("%Y-%m-%d")
                month_end_date = last_day.strftime("%Y-%m-%d")
                
                content = await self.memory_generator.generate_l5_content(
                    child_contents, previous_content,
                    year=year_val, month=month_val,
                    month_start=month_start_date, month_end=month_end_date
                )
                logger.info(f"✅ [L5Processor] LLM successfully generated L5 content, length: {len(content)} characters")
                generated_l5 = content
        except Exception as e:
            logger.error(f"❌ [L5Processor] L5 content generation failed: {e}", exc_info=True)
            raise
        
        child_ids = _get_memory_ids(valid_child_memories)
        
        valid_historical_memories = _filter_memories_by_level(historical_memories, "L5")
        historical_ids = _get_memory_ids(valid_historical_memories)
        
        year, month = (start_time_obj.year, start_time_obj.month) if start_time_obj else (timestamp.year, timestamp.month)

        final_created = None
        if time_window:
            end_time_val = time_window.get("end_time")
            if isinstance(end_time_val, str):
                final_created = self.time_manager.parse_iso_time(end_time_val)
            elif isinstance(end_time_val, datetime):
                final_created = end_time_val
        final_created = final_created or timestamp

        memory_params = {
            "level": MemoryLevel.L5,
            "user_id": user_id,
            "expert_id": expert_id,
            "title": title,
            "content": content,
            "created_at": final_created if isinstance(final_created, datetime) else self.time_manager.get_current_time(),
            "updated_at": final_created if isinstance(final_created, datetime) else self.time_manager.get_current_time(),
            "year": year,
            "month": month,
            "child_memory_ids": child_ids,
            "historical_memory_ids": historical_ids,
        }
        
        if time_window:
            if "start_time" in time_window:
                memory_params["time_window_start"] = time_window["start_time"]
            if "end_time" in time_window:
                memory_params["time_window_end"] = time_window["end_time"]

        memory = create_memory_by_level(**memory_params)
        
        logger.info(f"✅ [L5Processor] L5 memory generation completed: id={memory.id}")
        return memory

