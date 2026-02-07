"""
TiMem Session Context Manager

Responsible for managing dialogue context concatenation strategy:
1. Last 10 turns: Use original text context concatenation
2. Turns 11-20: Use in-session history memory concatenation
3. Others: Use retrieval workflow to search memory library within entire user-expert group
4. Deduplication: Remove duplicates between retrieved and existing window context
5. Time-ordered concatenation

Final form: [Session context + Session compressed memory] + [Global relevant memories]
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import hashlib

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_storage_config
from timem.workflows.memory_retrieval import run_memory_retrieval
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

logger = get_logger(__name__)


@dataclass
class DialogueTurn:
    """Dialogue turn"""
    turn_id: str  # Turn ID
    session_id: str  # Session ID
    user_id: str  # User ID
    expert_id: str  # Expert ID
    turn_index: int  # Turn index (starting from 0)
    user_message: str  # User message
    assistant_message: str  # Assistant reply
    timestamp: datetime  # Timestamp
    metadata: Optional[Dict[str, Any]] = None  # Metadata
    memory_id: Optional[str] = None  # Associated L1 memory ID


@dataclass
class ContextWindow:
    """Context window"""
    recent_turns: List[DialogueTurn]  # Last 10 turns (original text)
    compressed_turns: List[Dict[str, Any]]  # Turns 11-20 (compressed memory)
    retrieved_memories: List[Dict[str, Any]]  # Relevant memories retrieved from full library
    total_turns: int  # Total number of turns
    context_length: int  # Total context length (character count)
    thinking_event: Optional[Any] = None  # Thinking event returned by retrieval workflow (single, backward compatible)
    thinking_events: Optional[List[Dict[str, Any]]] = None  # List of thinking events from retrieval workflow (query understanding, strategy selection, etc.)


class SessionContextManager:
    """
    Session Context Manager
    
    Responsible for intelligent concatenation of dialogue context, supporting:
    - Original text window (last 10 turns)
    - Compressed memory window (turns 11-20)
    - Global memory retrieval
    - Intelligent deduplication
    - Time-ordered arrangement
    """
    
    def __init__(
        self,
        recent_window_size: int = 10,  # Recent window size
        compressed_window_size: int = 10,  # Compressed window size (turns 11-20)
        max_retrieved_memories: Optional[int] = None,  # Max retrieved memories (None reads from config file)
        enable_retrieval: bool = True,  # Whether to enable global retrieval
        dedup_threshold: float = 0.85,  # Deduplication similarity threshold
    ):
        """
        Initialize session context manager
        
        Args:
            recent_window_size: Recent original text window size (default 10 turns)
            compressed_window_size: Compressed window size (default 10 turns, i.e., turns 11-20)
            max_retrieved_memories: Max retrieved memories (None reads from config file)
            enable_retrieval: Whether to enable global memory retrieval
            dedup_threshold: Deduplication similarity threshold (0-1)
        """
        self.recent_window_size = recent_window_size
        self.compressed_window_size = compressed_window_size
        self.max_retrieved_memories = max_retrieved_memories
        self.enable_retrieval = enable_retrieval
        self.dedup_threshold = dedup_threshold
        
        # Load retrieval config from configuration file
        self._load_retrieval_config()
        
        self.engine = None  # Database engine
        self.session_factory = None  # Session factory
        
        logger.info(
            f"Initialize session context manager: "
            f"recent_window={recent_window_size}, "
            f"compressed_window={compressed_window_size}, "
            f"max_retrieved={self.max_retrieved_memories}"
        )
    
    def _load_retrieval_config(self):
        """Load retrieval config from configuration file"""
        try:
            from timem.utils.retrieval_config_manager import get_retrieval_config_manager
            
            # Get retrieval config manager
            config_manager = get_retrieval_config_manager()
            
            # Get simple retrieval strategy config
            simple_config = config_manager.get_strategy_config("simple")
            final_limits = simple_config.get("final_limits", {})
            
            # Calculate total memory count
            l1_count = final_limits.get("L1", 5)
            l2_count = final_limits.get("L2", 4)
            total_memories = l1_count + l2_count
            
            # If max_retrieved_memories not specified, use config file value
            if self.max_retrieved_memories is None:
                self.max_retrieved_memories = total_memories
                logger.info(f"Loaded retrieval config from file: L1={l1_count}, L2={l2_count}, Total={total_memories}")
            else:
                logger.info(f"Using specified retrieval config: {self.max_retrieved_memories} memories")
            
            # Save config for later use
            self.retrieval_config = {
                "simple": simple_config,
                "total_memories": total_memories,
                "l1_count": l1_count,
                "l2_count": l2_count
            }
            
        except Exception as e:
            logger.warning(f"Failed to load retrieval config, using default: {e}")
            if self.max_retrieved_memories is None:
                self.max_retrieved_memories = 5  # Default value
            self.retrieval_config = {
                "simple": {"final_limits": {"L1": 5, "L2": 4}},
                "total_memories": 9,
                "l1_count": 5,
                "l2_count": 4
            }
    
    async def _ensure_storage(self):
        """Ensure storage instance is initialized"""
        if self.engine is None:
            # Get config
            config = get_storage_config()
            sql_config = config.get('sql', {})
            postgres_config = sql_config.get('postgres', {})
            
            host = postgres_config.get('host', 'localhost')
            port = postgres_config.get('port', 5432)
            database = postgres_config.get('database', 'timem_db')
            user = postgres_config.get('user', 'timem_user')
            password = postgres_config.get('password', 'timem_password')
            
            connection_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
            
            self.engine = create_async_engine(
                connection_url,
                echo=False,
                pool_pre_ping=True
            )
            
            self.session_factory = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("Database connection initialized")
    
    async def store_dialogue_turn(
        self,
        session_id: str,
        user_id: str,
        expert_id: str,
        user_message: str,
        assistant_message: str,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None
    ) -> DialogueTurn:
        """
        Store dialogue turn
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            user_message: User message
            assistant_message: Assistant reply
            metadata: Metadata
            memory_id: Associated L1 memory ID
            
        Returns:
            DialogueTurn object
        """
        await self._ensure_storage()
        
        # Generate turn ID
        turn_id = f"turn_{hashlib.md5(f'{session_id}_{datetime.now().isoformat()}'.encode()).hexdigest()[:12]}"
        
        # Get current session turn count
        turn_index = await self._get_session_turn_count(session_id)
        
        # Create dialogue turn object
        dialogue_turn = DialogueTurn(
            turn_id=turn_id,
            session_id=session_id,
            user_id=user_id,
            expert_id=expert_id,
            turn_index=turn_index,
            user_message=user_message,
            assistant_message=assistant_message,
            timestamp=datetime.now(),
            metadata=metadata or {},
            memory_id=memory_id
        )
        
        # Store to database
        await self._store_turn_to_db(dialogue_turn)
        
        # Update user-expert state table (record last interaction time for scheduled scan)
        await self._update_user_expert_state(
            user_id=user_id,
            expert_id=expert_id,
            session_id=session_id,
            interaction_time=dialogue_turn.timestamp
        )
        
        logger.info(f"Store dialogue turn: session={session_id}, turn={turn_index}, turn_id={turn_id}")
        
        return dialogue_turn
    
    async def _get_session_turn_count(self, session_id: str) -> int:
        """Get dialogue turn count for session"""
        await self._ensure_storage()
        
        query = text("""
        SELECT COUNT(*) as count
        FROM dialogue_turns
        WHERE session_id = :session_id
        """)
        
        async with self.session_factory() as session:
            result = await session.execute(query, {"session_id": session_id})
            row = result.fetchone()
            return row[0] if row else 0
    
    async def _store_turn_to_db(self, dialogue_turn: DialogueTurn):
        """Store dialogue turn to database"""
        await self._ensure_storage()
        
        # First ensure table exists
        await self._ensure_dialogue_turns_table()
        
        query = text("""
        INSERT INTO dialogue_turns (
            turn_id, session_id, user_id, expert_id, turn_index,
            user_message, assistant_message, timestamp, metadata, memory_id
        ) VALUES (:turn_id, :session_id, :user_id, :expert_id, :turn_index,
                 :user_message, :assistant_message, :timestamp, :metadata, :memory_id)
        """)
        
        import json
        async with self.session_factory() as session:
            await session.execute(query, {
                "turn_id": dialogue_turn.turn_id,
                "session_id": dialogue_turn.session_id,
                "user_id": dialogue_turn.user_id,
                "expert_id": dialogue_turn.expert_id,
                "turn_index": dialogue_turn.turn_index,
                "user_message": dialogue_turn.user_message,
                "assistant_message": dialogue_turn.assistant_message,
                "timestamp": dialogue_turn.timestamp,
                "metadata": json.dumps(dialogue_turn.metadata) if dialogue_turn.metadata else "{}",
                "memory_id": dialogue_turn.memory_id
            })
            await session.commit()
    
    async def _ensure_dialogue_turns_table(self):
        """Ensure dialogue_turns table exists"""
        # Table created via migration script, just check here
        await self._ensure_storage()
        logger.debug("dialogue_turns table check (should be created via migration script)")
    
    async def _update_user_expert_state(
        self,
        user_id: str,
        expert_id: str,
        session_id: str,
        interaction_time: datetime
    ):
        """
        Update user-expert state table (for scheduled scan)
        
        Record last interaction time and session ID for scheduled scanner to detect sessions needing L2 memory generation
        """
        await self._ensure_storage()
        
        # Generate unique ID
        state_id = f"{user_id}_{expert_id}"
        
        # Use UPSERT syntax to update or insert
        query = text("""
        INSERT INTO user_expert_states (
            id, user_id, expert_id, last_session_id, last_interaction_time, 
            total_sessions, created_at, updated_at
        ) VALUES (
            :id, :user_id, :expert_id, :session_id, :interaction_time,
            1, :now, :now
        )
        ON CONFLICT (user_id, expert_id) 
        DO UPDATE SET
            last_session_id = :session_id,
            last_interaction_time = :interaction_time,
            updated_at = :now
        """)
        
        async with self.session_factory() as session:
            await session.execute(query, {
                "id": state_id,
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "interaction_time": interaction_time,
                "now": datetime.now()
            })
            await session.commit()
        
        logger.debug(f"Update user-expert state: {state_id}, session={session_id}, time={interaction_time}")
    
    async def get_session_context(
        self,
        session_id: str,
        user_id: str,
        expert_id: str,
        current_message: str,
        enable_global_retrieval: Optional[bool] = None,
        return_memories_only: bool = True  # Control whether to return only memories
    ) -> ContextWindow:
        """
        Get session context window
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            current_message: Current user message
            enable_global_retrieval: Whether to enable global retrieval (None uses default config)
            return_memories_only: Whether to return only memories (don't call LLM to generate answer)
                - True: Retrieval workflow returns memories directly without calling LLM (default, for dialogue systems)
                - False: Retrieval workflow calls LLM to generate QA answer (for standalone QA systems)
            
        Returns:
            ContextWindow object
        """
        await self._ensure_storage()
        
        # 1. Get recent dialogue turns (original text)
        recent_turns = await self._get_recent_turns(
            session_id, 
            self.recent_window_size
        )
        
        # 2. Get compressed memory turns (turns 11-20)
        compressed_turns = await self._get_compressed_turns(
            session_id,
            user_id,
            expert_id,
            start_offset=self.recent_window_size,
            limit=self.compressed_window_size
        )
        
        # 3. Global memory retrieval
        retrieved_memories = []
        thinking_event = None  # Receive thinking event (backward compatible)
        thinking_events = []  # Receive thinking events list
        if (enable_global_retrieval if enable_global_retrieval is not None else self.enable_retrieval):
            retrieved_memories, thinking_event, thinking_events = await self._retrieve_global_memories(
                user_id=user_id,
                expert_id=expert_id,
                query=current_message,
                max_results=self.max_retrieved_memories,
                return_memories_only=return_memories_only  # Key: pass parameter
            )
        
        # 4. Deduplication: remove memories overlapping with window context
        retrieved_memories = await self._deduplicate_memories(
            retrieved_memories,
            recent_turns,
            compressed_turns
        )
        
        # 5. Calculate total turns and context length
        total_turns = len(recent_turns) + len(compressed_turns)
        context_length = self._calculate_context_length(
            recent_turns,
            compressed_turns,
            retrieved_memories
        )
        
        context_window = ContextWindow(
            recent_turns=recent_turns,
            compressed_turns=compressed_turns,
            retrieved_memories=retrieved_memories,
            total_turns=total_turns,
            context_length=context_length,
            thinking_event=thinking_event,  # Pass thinking event (backward compatible)
            thinking_events=thinking_events  # Pass thinking events list (query understanding, strategy selection, etc.)
        )
        
        logger.info(
            f"Build context window: session={session_id}, "
            f"recent_turns={len(recent_turns)}, "
            f"compressed_turns={len(compressed_turns)}, "
            f"retrieved_memories={len(retrieved_memories)}, "
            f"thinking_events={len(thinking_events) if thinking_events else 0}, "
            f"total_length={context_length}"
        )
        
        # Debug: print thinking_events content
        if thinking_events:
            logger.info(f"Thinking events details: {thinking_events}")
        else:
            logger.warning(f"No thinking events retrieved! thinking_events = {thinking_events}")
        
        return context_window
    
    async def _get_recent_turns(
        self, 
        session_id: str, 
        limit: int
    ) -> List[DialogueTurn]:
        """Get recent dialogue turns (original text)"""
        await self._ensure_storage()
        
        query = text("""
        SELECT 
            turn_id, session_id, user_id, expert_id, turn_index,
            user_message, assistant_message, timestamp, metadata, memory_id
        FROM dialogue_turns
        WHERE session_id = :session_id
        ORDER BY turn_index DESC
        LIMIT :limit
        """)
        
        import json
        async with self.session_factory() as session:
            result = await session.execute(query, {"session_id": session_id, "limit": limit})
            rows = result.fetchall()
        
        # Convert to DialogueTurn objects and arrange in chronological order
        turns = []
        for row in reversed(rows):  # Reverse order to arrange chronologically
            metadata = row[8]  # metadata field
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}
            
            turns.append(DialogueTurn(
                turn_id=row[0],
                session_id=row[1],
                user_id=row[2],
                expert_id=row[3],
                turn_index=row[4],
                user_message=row[5],
                assistant_message=row[6],
                timestamp=row[7],
                metadata=metadata or {},
                memory_id=row[9]
            ))
        
        logger.debug(f"Get recent dialogue turns: session={session_id}, count={len(turns)}")
        
        return turns
    
    async def _get_compressed_turns(
        self,
        session_id: str,
        user_id: str,
        expert_id: str,
        start_offset: int,
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Get compressed memory turns (turns 11-20)
        
        Get from L1 memories here because L1 memories contain compressed dialogue content
        """
        await self._ensure_storage()
        
        # Get compressed memories from L1 memory table
        # Use memories view (already includes session_id)
        query = text("""
        SELECT 
            id, title, content, created_at, time_window_start, time_window_end
        FROM memories
        WHERE 
            user_id = :user_id 
            AND expert_id = :expert_id 
            AND session_id = :session_id
            AND level = 'L1'
        ORDER BY created_at DESC
        OFFSET :offset
        LIMIT :limit
        """)
        
        import json
        async with self.session_factory() as session:
            result = await session.execute(query, {
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "offset": start_offset,
                "limit": limit
            })
            rows = result.fetchall()
        
        # Convert to dictionary list and arrange in chronological order
        compressed_turns = []
        for row in reversed(rows):  # Reverse order to arrange chronologically
            compressed_turns.append({
                'id': row[0],
                'title': row[1],
                'content': row[2],
                'created_at': row[3],
                'time_window_start': row[4],
                'time_window_end': row[5],
                'level': 'L1',
                'source': 'compressed'
            })
        
        logger.debug(
            f"Get compressed memory turns: session={session_id}, "
            f"offset={start_offset}, count={len(compressed_turns)}"
        )
        
        return compressed_turns
    
    async def _retrieve_global_memories(
        self,
        user_id: str,
        expert_id: str,
        query: str,
        max_results: int,
        return_memories_only: bool = True  # Default: return only memories, don't call LLM
    ) -> Tuple[List[Dict[str, Any]], Optional[Any]]:
        """
        Retrieve relevant memories from global memory library
        
        Use existing memory retrieval workflow
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            query: Retrieval query
            max_results: Maximum result count
            return_memories_only: Whether to return only memories (don't call LLM to generate answer)
                - True: Return memory content and ID directly, don't block main process
                - False: Call LLM to generate QA answer (old mode)
                
        Returns:
            Tuple[List of retrieved memories, thinking event]
        """
        try:
            # Build retrieval config using settings loaded from config file
            retrieval_config = {}
            if hasattr(self, 'retrieval_config') and self.retrieval_config:
                retrieval_config = {
                    "simple": self.retrieval_config["simple"]
                }
                logger.info(f"Using config file retrieval settings: L1={self.retrieval_config['l1_count']}, L2={self.retrieval_config['l2_count']}")
            
            retrieval_result = await run_memory_retrieval(
                input_data={
                    "question": query,
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "return_memories_only": return_memories_only,  # Pass config
                    "skip_llm_generation": return_memories_only,   # Pass config (compatibility)
                    "retrieval_config": retrieval_config           # Pass retrieval config
                },
                debug_mode=False,
                use_v2_retrievers=True
            )
            
            # Get retrieved memories
            retrieved_memories = retrieval_result.get("retrieved_memories", [])
            
            # Get thinking event (backward compatible)
            thinking_event = retrieval_result.get("thinking_event", None)
            
            # Get thinking events list (query understanding, strategy selection, etc.)
            thinking_events = retrieval_result.get("thinking_events", [])
            
            if return_memories_only:
                logger.info(f"Memory-only mode: skip LLM generation, return {len(retrieved_memories)} memories, {len(thinking_events)} thinking events")
            else:
                logger.info(f"Traditional QA mode: call LLM to generate answer based on {len(retrieved_memories)} memories")
            
            # Limit count
            if len(retrieved_memories) > max_results:
                retrieved_memories = retrieved_memories[:max_results]
            
            # Add source tag and ensure required fields
            for memory in retrieved_memories:
                memory['source'] = 'global_retrieval'
                # Ensure session_id is included (for frontend highlighting)
                if 'session_id' not in memory or not memory['session_id']:
                    # Try to extract from metadata
                    if 'metadata' in memory and isinstance(memory['metadata'], dict):
                        memory['session_id'] = memory['metadata'].get('session_id', '')
            
            logger.info(f"Global memory retrieval completed: query={query[:50]}..., count={len(retrieved_memories)}, thinking_events={len(thinking_events)}, return_memories_only={return_memories_only}")
            
            # Return memories and thinking events (add thinking_events)
            return (retrieved_memories, thinking_event, thinking_events)
            
        except Exception as e:
            logger.error(f"Global memory retrieval failed: {e}", exc_info=True)
            return [], None, []  # Return empty list, None, empty list
    
    async def _deduplicate_memories(
        self,
        retrieved_memories: List[Dict[str, Any]],
        recent_turns: List[DialogueTurn],
        compressed_turns: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Deduplication: remove memories overlapping with window context
        
        Deduplication strategy:
        1. Exact deduplication based on memory_id
        2. Fuzzy deduplication based on content similarity (using simple text similarity)
        """
        if not retrieved_memories:
            return []
        
        # 1. Collect memory IDs in window
        window_memory_ids = set()
        
        # Collect memory_id from recent_turns
        for turn in recent_turns:
            if turn.memory_id:
                window_memory_ids.add(turn.memory_id)
        
        # Collect memory_id from compressed_turns
        for turn in compressed_turns:
            memory_id = turn.get('id')
            if memory_id:
                window_memory_ids.add(memory_id)
        
        # 2. Collect window content texts (for similarity comparison)
        window_texts = []
        
        # Collect texts from recent_turns
        for turn in recent_turns:
            window_texts.append(turn.user_message)
            window_texts.append(turn.assistant_message)
        
        # Collect texts from compressed_turns
        for turn in compressed_turns:
            content = turn.get('content', '')
            if content:
                window_texts.append(content)
        
        # 3. Perform deduplication
        deduplicated_memories = []
        
        for memory in retrieved_memories:
            memory_id = memory.get('id')
            memory_content = memory.get('content', '')
            
            # Exact ID deduplication
            if memory_id and memory_id in window_memory_ids:
                logger.debug(f"Dedup (ID match): memory_id={memory_id}")
                continue
            
            # Content similarity deduplication
            is_duplicate = False
            for window_text in window_texts:
                similarity = self._calculate_text_similarity(memory_content, window_text)
                if similarity >= self.dedup_threshold:
                    logger.debug(
                        f"Dedup (content similar): memory_id={memory_id}, "
                        f"similarity={similarity:.2f}"
                    )
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduplicated_memories.append(memory)
        
        removed_count = len(retrieved_memories) - len(deduplicated_memories)
        if removed_count > 0:
            logger.info(f"Deduplication completed: removed {removed_count} duplicate memories")
        
        return deduplicated_memories
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts (simple implementation using Jaccard similarity)
        
        Args:
            text1: Text 1
            text2: Text 2
            
        Returns:
            Similarity score (0-1)
        """
        if not text1 or not text2:
            return 0.0
        
        # Convert to character sets
        set1 = set(text1.lower())
        set2 = set(text2.lower())
        
        # Calculate Jaccard similarity
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def _calculate_context_length(
        self,
        recent_turns: List[DialogueTurn],
        compressed_turns: List[Dict[str, Any]],
        retrieved_memories: List[Dict[str, Any]]
    ) -> int:
        """Calculate total context length (character count)"""
        length = 0
        
        # Calculate recent_turns length
        for turn in recent_turns:
            length += len(turn.user_message) + len(turn.assistant_message)
        
        # Calculate compressed_turns length
        for turn in compressed_turns:
            content = turn.get('content', '')
            length += len(content)
        
        # Calculate retrieved_memories length
        for memory in retrieved_memories:
            content = memory.get('content', '')
            length += len(content)
        
        return length
    
    def format_context_for_llm(
        self,
        context_window: ContextWindow,
        include_metadata: bool = False
    ) -> str:
        """
        Format context as LLM input format
        
        Args:
            context_window: Context window
            include_metadata: Whether to include metadata
            
        Returns:
            Formatted context string
        """
        formatted_parts = []
        
        # 1. Add recent dialogue (original text)
        if context_window.recent_turns:
            formatted_parts.append("### Recent Dialogue History (Original) ###\n")
            
            for turn in context_window.recent_turns:
                formatted_parts.append(f"[Turn {turn.turn_index}]")
                formatted_parts.append(f"User says: {turn.user_message}")
                formatted_parts.append(f"Expert replies: {turn.assistant_message}")
                
                if include_metadata and turn.metadata:
                    formatted_parts.append(f"Metadata: {turn.metadata}")
                
                formatted_parts.append("")  # Empty line
        
        # 2. Add compressed memory (turns 11-20)
        if context_window.compressed_turns:
            formatted_parts.append("\n### Session History Memory (Compressed) ###\n")
            formatted_parts.append("Below is a summary of previous conversations with the current user:\n")
            
            for idx, turn in enumerate(context_window.compressed_turns, 1):
                title = turn.get('title', f'Historical Dialogue {idx}')
                content = turn.get('content', '')
                
                formatted_parts.append(f"[{title}]")
                formatted_parts.append(content)
                
                if include_metadata and turn.get('metadata'):
                    formatted_parts.append(f"Metadata: {turn['metadata']}")
                
                formatted_parts.append("")  # Empty line
        
        # 3. Add global retrieved memories
        if context_window.retrieved_memories:
            formatted_parts.append("\n### Relevant Memories About Current User ###\n")
            formatted_parts.append("Below are retrieved memory information about the current user:\n")
            
            for idx, memory in enumerate(context_window.retrieved_memories, 1):
                level = memory.get('level', 'Unknown')
                title = memory.get('title', f'Memory {idx}')
                content = memory.get('content', '')
                
                formatted_parts.append(f"[{level}] {title}")
                formatted_parts.append(content)
                
                if include_metadata and memory.get('metadata'):
                    formatted_parts.append(f"Metadata: {memory['metadata']}")
                
                formatted_parts.append("")  # Empty line
        
        # 4. Add statistics
        if include_metadata:
            formatted_parts.append("\n### Context Statistics ###")
            formatted_parts.append(f"Total turns: {context_window.total_turns}")
            formatted_parts.append(f"Recent dialogue: {len(context_window.recent_turns)} turns")
            formatted_parts.append(f"Compressed memory: {len(context_window.compressed_turns)} items")
            formatted_parts.append(f"Retrieved memory: {len(context_window.retrieved_memories)} items")
            formatted_parts.append(f"Total length: {context_window.context_length} characters")
        
        return "\n".join(formatted_parts)


# Global singleton
_session_context_manager = None


async def get_session_context_manager() -> SessionContextManager:
    """Get session context manager singleton"""
    global _session_context_manager
    
    if _session_context_manager is None:
        _session_context_manager = SessionContextManager()
        # Immediately initialize database connection to avoid first request delay
        await _session_context_manager._ensure_storage()
        logger.info("SessionContextManager initialized and warmed up")
    
    return _session_context_manager

