"""
TiMem Memory Generation Service - Engineering Architecture Best Practices

Online service architecture based on FastAPI and LangGraph, solving instance conflict issues in parallel scenarios.

Core design principles:
1. Singleton service pattern: globally unique memory generation service instance
2. Unified connection pool management: using global connection pool manager
3. State isolation: concurrent safety through ExecutionState
4. Resource lifecycle management: unified service startup and shutdown
5. High availability: support for hot reload and fault recovery
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Union
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import threading
from dataclasses import dataclass
from enum import Enum

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from timem.workflows.memory_generation import MemoryGenerationWorkflow
from storage.memory_storage_manager import MemoryStorageManager
from timem.core.execution_state import ExecutionState
from timem.core.global_connection_pool import get_global_pool_manager
from timem.utils.logging import get_logger, get_safe_logger
from timem.utils.config_manager import get_config

logger = get_logger(__name__)

class ServiceStatus(Enum):
    """Service status enumeration"""
    INITIALIZING = "initializing"
    READY = "ready"
    DEGRADED = "degraded"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"

@dataclass
class ServiceMetrics:
    """Service metrics"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    active_workflows: int = 0
    avg_processing_time: float = 0.0
    last_health_check: Optional[datetime] = None
    connection_pool_utilization: float = 0.0

class MemoryGenerationRequest(BaseModel):
    """Memory generation request - supports multiple input formats"""
    # Basic information
    user_id: str = Field(..., description="User ID")
    expert_id: str = Field(..., description="Expert ID")
    session_id: str = Field(..., description="Session ID")
    content: str = Field(..., description="Dialogue content")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp")
    
    # Optional information
    speakers: Optional[List[str]] = Field(None, description="List of speakers")
    conv_id: Optional[str] = Field(None, description="Conversation ID")
    turn_idx: Optional[int] = Field(None, description="Dialogue turn index")
    date_time: Optional[str] = Field(None, description="Original time string")
    
    # Advanced configuration
    execution_state: Optional[Dict[str, Any]] = Field(None, description="Execution state")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata")
    debug_mode: bool = Field(False, description="Debug mode")
    
    # Workflow control
    force_generate_all_levels: bool = Field(False, description="Force generate all level memories")
    skip_history_collection: bool = Field(False, description="Skip history memory collection")
    custom_workflow_config: Optional[Dict[str, Any]] = Field(None, description="Custom workflow config")

class ConversationProcessingRequest(BaseModel):
    """Conversation processing request - for processing entire conversation"""
    conv_id: str = Field(..., description="Conversation ID")
    speakers: List[str] = Field(..., description="List of speakers")
    sessions: List[Dict[str, Any]] = Field(..., description="List of session data")
    user_id: Optional[str] = Field(None, description="User ID (auto-generated if empty)")
    expert_id: Optional[str] = Field(None, description="Expert ID (auto-generated if empty)")
    processing_config: Optional[Dict[str, Any]] = Field(None, description="Processing config")

class BatchConversationRequest(BaseModel):
    """Batch conversation processing request"""
    conversations: List[ConversationProcessingRequest] = Field(..., description="List of conversations")
    parallel: bool = Field(True, description="Whether to process in parallel")
    max_concurrent: int = Field(10, description="Maximum concurrent count")
    global_config: Optional[Dict[str, Any]] = Field(None, description="Global config")

class MemoryGenerationResponse(BaseModel):
    """Memory generation response"""
    success: bool = Field(..., description="Whether successful")
    memories: List[Dict[str, Any]] = Field(default_factory=list, description="Generated memories")
    processing_time: float = Field(..., description="Processing time (seconds)")
    workflow_id: str = Field(..., description="Workflow instance ID")
    error: Optional[str] = Field(None, description="Error message")
    
    # Extended information
    memory_levels: Dict[str, int] = Field(default_factory=dict, description="Memory count by level")
    session_info: Optional[Dict[str, Any]] = Field(None, description="Session info")
    user_info: Optional[Dict[str, Any]] = Field(None, description="User info")

class ConversationProcessingResponse(BaseModel):
    """Conversation processing response"""
    conv_id: str = Field(..., description="Conversation ID")
    success: bool = Field(..., description="Whether successful")
    turns_processed: int = Field(0, description="Dialogue turns processed")
    sessions_processed: int = Field(0, description="Sessions processed")
    total_memories: int = Field(0, description="Total memories")
    memory_levels: Dict[str, int] = Field(default_factory=dict, description="Memory count by level")
    processing_time: float = Field(..., description="Processing time (seconds)")
    user_id: str = Field(..., description="User ID")
    expert_id: str = Field(..., description="Expert ID")
    speakers: List[str] = Field(..., description="List of speakers")
    error: Optional[str] = Field(None, description="Error message")
    session_details: List[Dict[str, Any]] = Field(default_factory=list, description="Session details")

class BatchConversationResponse(BaseModel):
    """Batch conversation processing response"""
    success: bool = Field(..., description="Overall success")
    total_conversations: int = Field(..., description="Total conversations")
    successful_conversations: int = Field(..., description="Successful conversations")
    failed_conversations: int = Field(..., description="Failed conversations")
    total_turns_processed: int = Field(..., description="Total turns processed")
    total_memories_generated: int = Field(..., description="Total memories generated")
    total_processing_time: float = Field(..., description="Total processing time (seconds)")
    results: List[ConversationProcessingResponse] = Field(..., description="List of processing results")
    performance_metrics: Dict[str, Any] = Field(default_factory=dict, description="Performance metrics")


class ServiceHealthResponse(BaseModel):
    """Service health check response"""
    status: ServiceStatus = Field(..., description="Service status")
    uptime: float = Field(..., description="Uptime (seconds)")
    metrics: ServiceMetrics = Field(..., description="Service metrics")
    dependencies: Dict[str, bool] = Field(..., description="Dependency service status")


class MemoryGenerationService:
    """
    Memory generation service - singleton pattern
    
    Core features:
    1. Globally unique instance, avoiding duplicate creation
    2. Unified connection pool management
    3. Concurrent-safe state management
    4. Automatic fault recovery
    5. Resource lifecycle management
    """
    
    _instance: Optional['MemoryGenerationService'] = None
    _lock = asyncio.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryGenerationService, cls).__new__(cls)
            cls._instance._initialize_instance()
        return cls._instance
    
    def _initialize_instance(self):
        """Initialize instance variables"""
        self.status = ServiceStatus.INITIALIZING
        self.start_time = datetime.now()
        self.metrics = ServiceMetrics()
        self.workflow: Optional[MemoryGenerationWorkflow] = None
        self.storage_manager: Optional[MemoryStorageManager] = None
        self.pool_manager = None
        self._active_workflows: Dict[str, asyncio.Task] = {}
        self._workflow_counter = 0
        self._logger = get_safe_logger()
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> bool:
        """Initialize service"""
        if self._initialized:
            return True
            
        async with self._lock:
            if self._initialized:
                return True
                
            try:
                self._logger.info("Starting memory generation service initialization...")
                
                # 1. Initialize global connection pool manager
                self.pool_manager = await get_global_pool_manager()
                if not await self.pool_manager.health_check():
                    raise RuntimeError("Global connection pool unavailable")
                
                # 2. Initialize storage manager (using global connection pool)
                self.storage_manager = MemoryStorageManager()
                await self.storage_manager._create_default_adapters()
                
                # 3. Initialize workflow (singleton mode)
                self.workflow = await MemoryGenerationWorkflow.create(debug_mode=False)
                
                # 4. Update status
                self.status = ServiceStatus.READY
                self._initialized = True
                
                self._logger.info("Memory generation service initialized successfully")
                return True
                
            except Exception as e:
                self.status = ServiceStatus.ERROR
                self._logger.error(f"Memory generation service initialization failed: {e}")
                raise
    
    async def generate_memory(self, request: MemoryGenerationRequest) -> MemoryGenerationResponse:
        """
        Generate memory - core business method (with memory validation and retry mechanism)
        
        Args:
            request: Memory generation request
            
        Returns:
            Memory generation response
        """
        if not self._initialized or self.status != ServiceStatus.READY:
            await self.initialize()
        
        if self.status != ServiceStatus.READY:
            raise HTTPException(
                status_code=503,
                detail=f"Service unavailable, current status: {self.status.value}"
            )
        
        start_time = datetime.now()
        workflow_id = f"wf_{self._workflow_counter}_{int(start_time.timestamp())}"
        self._workflow_counter += 1
        
        # Memory generation retry mechanism
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count <= max_retries:
            try:
                # Update metrics
                self.metrics.total_requests += 1
                self.metrics.active_workflows += 1
                
                # Build execution state (ensure concurrent isolation)
                execution_state = ExecutionState(
                    user_id=request.user_id,
                    expert_id=request.expert_id,
                    context_id=f"{request.session_id}_{workflow_id}"
                )
                
                # Build workflow input
                workflow_input = {
                    "user_id": request.user_id,
                    "expert_id": request.expert_id,
                    "session_id": request.session_id,
                    "content": request.content,
                    "timestamp": request.timestamp,
                    "execution_state": execution_state,
                    "metadata": request.metadata or {}
                }
                
                # Execute workflow
                result = await self.workflow.run(workflow_input)
                
                # Validate generated memories
                validation_result = await self._validate_generated_memories(result, request)
                
                if validation_result["is_valid"]:
                    # Memory validation passed, calculate processing time and return result
                    processing_time = (datetime.now() - start_time).total_seconds()
                    
                    # Count memory levels
                    memories = result.get("generated_memories", [])
                    memory_levels = {}
                    for memory in memories:
                        level = memory.get("level", "Unknown")
                        memory_levels[level] = memory_levels.get(level, 0) + 1
                    
                    # Update metrics
                    if result.get("success", False):
                        self.metrics.successful_requests += 1
                    else:
                        self.metrics.failed_requests += 1
                    
                    # Update average processing time
                    total_processed = self.metrics.successful_requests + self.metrics.failed_requests
                    if total_processed > 0:
                        self.metrics.avg_processing_time = (
                            (self.metrics.avg_processing_time * (total_processed - 1) + processing_time) 
                            / total_processed
                        )
                    
                    return MemoryGenerationResponse(
                        success=result.get("success", False),
                        memories=memories,
                        processing_time=processing_time,
                        workflow_id=workflow_id,
                        error=result.get("error"),
                        memory_levels=memory_levels,
                        session_info={
                            "session_id": request.session_id,
                            "user_id": request.user_id,
                            "expert_id": request.expert_id
                        },
                        user_info={
                            "user_id": request.user_id,
                            "expert_id": request.expert_id
                        }
                    )
                else:
                    # Memory validation failed, prepare to retry
                    last_error = validation_result["error_message"]
                    retry_count += 1
                    
                    if retry_count <= max_retries:
                        # Clean up possibly stored invalid memories
                        await self._cleanup_invalid_memories(result, request)
                        
                        # Wait and retry
                        wait_time = 2.0 * retry_count
                        self._logger.warning(f"Memory validation failed, retry in {wait_time:.1f}s (attempt {retry_count}/{max_retries}): {last_error}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Retries exhausted, return failure
                        self._logger.error(f"Memory generation failed after {max_retries} retries: {last_error}")
                        self.metrics.failed_requests += 1
                        
                        return MemoryGenerationResponse(
                            success=False,
                            memories=[],
                            processing_time=(datetime.now() - start_time).total_seconds(),
                            workflow_id=workflow_id,
                            error=f"Memory generation failed after {max_retries} retries: {last_error}",
                            memory_levels={},
                            session_info={
                                "session_id": request.session_id,
                                "user_id": request.user_id,
                                "expert_id": request.expert_id
                            },
                            user_info={
                                "user_id": request.user_id,
                                "expert_id": request.expert_id
                            }
                        )
                        
            except Exception as e:
                last_error = f"Workflow execution exception: {str(e)}"
                retry_count += 1
                
                if retry_count <= max_retries:
                    wait_time = 2.0 * retry_count
                    self._logger.warning(f"Workflow execution exception, retry in {wait_time:.1f}s (attempt {retry_count}/{max_retries}): {last_error}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Retries exhausted, return failure
                    self._logger.error(f"Workflow execution failed after {max_retries} retries: {last_error}")
                    self.metrics.failed_requests += 1
                    
                    return MemoryGenerationResponse(
                        success=False,
                        memories=[],
                        processing_time=(datetime.now() - start_time).total_seconds(),
                        workflow_id=workflow_id,
                        error=f"Workflow execution failed after {max_retries} retries: {last_error}",
                        memory_levels={},
                        session_info={
                            "session_id": request.session_id,
                            "user_id": request.user_id,
                            "expert_id": request.expert_id
                        },
                        user_info={
                            "user_id": request.user_id,
                            "expert_id": request.expert_id
                        }
                    )
            
            finally:
                self.metrics.active_workflows = max(0, self.metrics.active_workflows - 1)
    
    async def _validate_generated_memories(self, result: Dict[str, Any], request: MemoryGenerationRequest) -> Dict[str, Any]:
        """
        Validate whether generated memories are valid
        
        Args:
            result: Workflow execution result
            request: Original request
            
        Returns:
            Validation result dictionary with is_valid and error_message fields
        """
        try:
            # Check if workflow executed successfully
            if not result.get("success", False):
                return {
                    "is_valid": False,
                    "error_message": f"Workflow execution failed: {result.get('error', 'Unknown error')}"
                }
            
            # Get generated memories
            memories = result.get("generated_memories", [])
            
            # Check if any memories were generated
            if not memories:
                return {
                    "is_valid": False,
                    "error_message": "No memories generated"
                }
            
            # Validate validity of each memory
            valid_memories = []
            invalid_memories = []
            
            for i, memory in enumerate(memories):
                if memory is None:
                    invalid_memories.append(f"Memory[{i}] is None")
                    continue
                
                # Check if memory is dictionary format
                if not isinstance(memory, dict):
                    invalid_memories.append(f"Memory[{i}] is not dictionary format: {type(memory)}")
                    continue
                
                # Check required fields
                required_fields = ["id", "level", "content", "user_id", "expert_id"]
                missing_fields = []
                for field in required_fields:
                    if field not in memory or not memory[field]:
                        missing_fields.append(field)
                
                if missing_fields:
                    invalid_memories.append(f"Memory[{i}] missing required fields: {missing_fields}")
                    continue
                
                # Check if content is empty
                content = memory.get("content", "").strip()
                if not content:
                    invalid_memories.append(f"Memory[{i}] content is empty: ID={memory.get('id')}")
                    continue
                
                # Check if memory ID is valid
                memory_id = memory.get("id", "").strip()
                if not memory_id:
                    invalid_memories.append(f"Memory[{i}] ID is empty")
                    continue
                
                # Check time fields
                has_time_fields = ("created_at" in memory) or ("time_window_start" in memory)
                if not has_time_fields:
                    invalid_memories.append(f"Memory[{i}] missing time fields")
                    continue
                
                valid_memories.append(memory)
            
            # Determine validation result
            if not valid_memories:
                error_msg = f"All memories are invalid: {invalid_memories}"
                return {
                    "is_valid": False,
                    "error_message": error_msg
                }
            
            if invalid_memories:
                self._logger.warning(f"Some memories are invalid: {invalid_memories}")
            
            return {
                "is_valid": True,
                "error_message": "",
                "valid_memories": valid_memories,
                "invalid_memories": invalid_memories
            }
            
        except Exception as e:
            error_msg = f"Memory validation exception: {str(e)}"
            self._logger.error(error_msg)
            return {
                "is_valid": False,
                "error_message": error_msg
            }
    
    async def _cleanup_invalid_memories(self, result: Dict[str, Any], request: MemoryGenerationRequest):
        """
        Clean up invalid memories
        
        Args:
            result: Workflow execution result
            request: Original request
        """
        try:
            memories = result.get("generated_memories", [])
            if not memories:
                return
            
            self._logger.info(f"Starting cleanup of invalid memories, total {len(memories)} items")
            
            cleanup_count = 0
            for memory in memories:
                try:
                    if not isinstance(memory, dict):
                        continue
                    
                    memory_id = memory.get("id")
                    if not memory_id:
                        continue
                    
                    # Use storage manager to delete invalid memories
                    delete_result = await self.storage_manager.delete_memory(
                        memory_id=memory_id,
                        level=memory.get("level", "L1"),
                        storage_types=["sql", "vector"]
                    )
                    
                    if delete_result.get("success", False):
                        cleanup_count += 1
                        self._logger.debug(f"Successfully cleaned up invalid memory: {memory_id}")
                    else:
                        self._logger.warning(f"Failed to clean up invalid memory: {memory_id}")
                        
                except Exception as e:
                    self._logger.warning(f"Exception cleaning up memory: {e}")
            
            if cleanup_count > 0:
                self._logger.info(f"Successfully cleaned up {cleanup_count} invalid memories")
            else:
                self._logger.info("No memories need cleanup")
                
        except Exception as e:
            self._logger.error(f"Failed to clean up invalid memories: {e}")
    
    async def run_backfill(
        self,
        tasks: List[Any],
        progress_callback: Optional[Any] = None
    ) -> MemoryGenerationResponse:
        """
        Run backfill tasks - for batch backfill of L2-L5 memories
        
        This is a wrapper around the workflow's run_backfill method, providing a service-level interface.
        
        Args:
            tasks: BackfillTask list (sorted)
            progress_callback: Optional progress callback function
            
        Returns:
            MemoryGenerationResponse object containing backfill results
            
        Use cases:
        - Automatic backfill at midnight daily
        - L2 backfill between sessions
        - Manually triggered forced backfill
        """
        if not self._initialized or self.status != ServiceStatus.READY:
            await self.initialize()
        
        if self.status != ServiceStatus.READY:
            raise HTTPException(
                status_code=503,
                detail=f"Service unavailable, current status: {self.status.value}"
            )
        
        start_time = datetime.now()
        workflow_id = f"backfill_{self._workflow_counter}_{int(start_time.timestamp())}"
        self._workflow_counter += 1
        
        try:
            self._logger.info(f"Starting backfill tasks: {len(tasks)} tasks")
            
            # Update metrics
            self.metrics.total_requests += 1
            self.metrics.active_workflows += 1
            
            # Call workflow's run_backfill method
            result = await self.workflow.run_backfill(tasks, progress_callback)
            
            # Process return results
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Convert generated memories to unified format
            generated_memories = []
            memory_levels = {}
            
            for memory in result.get("generated_memories", []):
                # Convert Memory object to dictionary
                if hasattr(memory, 'to_dict'):
                    memory_dict = memory.to_dict()
                elif hasattr(memory, '__dict__'):
                    memory_dict = {
                        k: v for k, v in memory.__dict__.items()
                        if not k.startswith('_')
                    }
                else:
                    memory_dict = memory if isinstance(memory, dict) else {}
                
                generated_memories.append(memory_dict)
                
                # Count memory levels
                level = memory_dict.get("level", "Unknown")
                if hasattr(level, 'value'):
                    level = level.value
                memory_levels[str(level)] = memory_levels.get(str(level), 0) + 1
            
            # Determine success status
            success = result.get("success", 0) > 0 or len(generated_memories) > 0
            
            # Update metrics
            if success:
                self.metrics.successful_requests += 1
            else:
                self.metrics.failed_requests += 1
            
            # Build error information
            error_info = None
            if result.get("errors"):
                error_info = f"{result.get('failed', 0)} tasks failed, details: {result['errors'][:3]}"
            
            self._logger.info(
                f"Backfill tasks completed: {result.get('success', 0)}/{result.get('total', 0)} tasks successful, "
                f"generated {len(generated_memories)} memories"
            )
            
            return MemoryGenerationResponse(
                success=success,
                memories=generated_memories,
                processing_time=processing_time,
                workflow_id=workflow_id,
                error=error_info,
                memory_levels=memory_levels
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            self._logger.error(f"Backfill task execution failed: {e}", exc_info=True)
            self.metrics.failed_requests += 1
            
            return MemoryGenerationResponse(
                success=False,
                memories=[],
                processing_time=processing_time,
                workflow_id=workflow_id,
                error=f"Backfill task execution failed: {str(e)}",
                memory_levels={}
            )
            
        finally:
            self.metrics.active_workflows = max(0, self.metrics.active_workflows - 1)
    
    async def process_conversation(self, request: ConversationProcessingRequest) -> ConversationProcessingResponse:
        """
        Process entire conversation - end-to-end memory generation
        
        Args:
            request: Conversation processing request
            
        Returns:
            Conversation processing response
        """
        start_time = datetime.now()
        
        try:
            # 1. Validate user ID (must be provided by test code)
            if not request.user_id or not request.expert_id:
                raise ValueError(
                    f"Conversation {request.conv_id} missing user ID or expert ID. "
                    f"Please call user registration service to register user first, then provide user_id and expert_id."
                )
            
            user_id = request.user_id
            expert_id = request.expert_id
            
            # 2. Process all sessions
            total_turns_processed = 0
            total_memories = 0
            memory_levels = {}
            session_details = []
            all_sessions_successful = True
            processing_error = None
            
            for session_data in request.sessions:
                session_id = session_data.get("session_id", "unknown")
                dialogues = session_data.get("dialogues", [])
                date_time_str = session_data.get("date_time", "")
                
                # Parse time
                try:
                    from timem.utils.time_parser import time_parser
                    session_time = time_parser.parse(date_time_str)
                except Exception as e:
                    self._logger.warning(f"Failed to parse time {session_id}: {e}")
                    session_time = datetime.now()
                
                # Process dialogue turns
                session_turns = 0
                session_memories = 0
                session_memory_levels = {}
                
                max_turns = len(dialogues) // 2
                for turn_idx in range(1, max_turns + 1):
                    dialogue_start_idx = (turn_idx - 1) * 2
                    dialogue_end_idx = dialogue_start_idx + 1
                    
                    if dialogue_end_idx >= len(dialogues):
                        break
                    
                    # Build dialogue content
                    first_dialogue = dialogues[dialogue_start_idx]
                    second_dialogue = dialogues[dialogue_end_idx]
                    
                    first_text = first_dialogue.get("text", "")
                    second_text = second_dialogue.get("text", "")
                    first_speaker = first_dialogue.get("speaker", "")
                    second_speaker = second_dialogue.get("speaker", "")
                    
                    # Enhance text content (including image information)
                    first_text = self._extract_and_enhance_text_with_image_info(first_dialogue, first_text)
                    second_text = self._extract_and_enhance_text_with_image_info(second_dialogue, second_text)
                    
                    # Build dialogue content
                    turn_timestamp = session_time + timedelta(minutes=(turn_idx - 1) * 2)
                    content = f"{first_speaker}: {first_text}\n{second_speaker}: {second_text}"
                    
                    # Create memory generation request
                    memory_request = MemoryGenerationRequest(
                        user_id=user_id,
                        expert_id=expert_id,
                        session_id=f"{request.conv_id}_{session_id}",
                        content=content,
                        timestamp=turn_timestamp,
                        speakers=request.speakers,
                        conv_id=request.conv_id,
                        turn_idx=turn_idx,
                        date_time=date_time_str,
                        metadata={
                            "conv_id": request.conv_id,
                            "session_id": session_id,
                            "turn_idx": turn_idx,
                            "speakers": request.speakers,
                            "processing_config": request.processing_config
                        }
                    )
                    
                    # Generate memory
                    memory_response = await self.generate_memory(memory_request)
                    
                    if memory_response.success:
                        session_turns += 1
                        session_memories += len(memory_response.memories)
                        
                        # Count memory levels
                        for level, count in memory_response.memory_levels.items():
                            session_memory_levels[level] = session_memory_levels.get(level, 0) + count
                            memory_levels[level] = memory_levels.get(level, 0) + count
                    else:
                        if not processing_error:
                            processing_error = f"Session {session_id} turn {turn_idx} failed: {memory_response.error}"
                        all_sessions_successful = False
                
                # Record session details
                session_details.append({
                    "session_id": session_id,
                    "turns_processed": session_turns,
                    "memories_generated": session_memories,
                    "memory_levels": session_memory_levels,
                    "date_time": date_time_str,
                    "total_dialogues": len(dialogues)
                })
                
                total_turns_processed += session_turns
                total_memories += session_memories
            
            # 3. Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return ConversationProcessingResponse(
                conv_id=request.conv_id,
                success=all_sessions_successful and not processing_error,
                turns_processed=total_turns_processed,
                sessions_processed=len(request.sessions),
                total_memories=total_memories,
                memory_levels=memory_levels,
                processing_time=processing_time,
                user_id=user_id,
                expert_id=expert_id,
                speakers=request.speakers,
                error=processing_error,
                session_details=session_details
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            self._logger.error(f"Conversation processing failed {request.conv_id}: {e}")
            
            return ConversationProcessingResponse(
                conv_id=request.conv_id,
                success=False,
                turns_processed=0,
                sessions_processed=0,
                total_memories=0,
                memory_levels={},
                processing_time=processing_time,
                user_id=request.user_id or "",
                expert_id=request.expert_id or "",
                speakers=request.speakers,
                error=str(e),
                session_details=[]
            )
    
    async def process_batch_conversations(self, request: BatchConversationRequest) -> BatchConversationResponse:
        """
        Batch process conversations - support parallel processing
        
        Args:
            request: Batch conversation processing request
            
        Returns:
            Batch conversation processing response
        """
        start_time = datetime.now()
        
        try:
            if request.parallel and len(request.conversations) > 1:
                # Parallel processing
                semaphore = asyncio.Semaphore(request.max_concurrent)
                
                async def process_single_conversation(conv_request: ConversationProcessingRequest):
                    async with semaphore:
                        return await self.process_conversation(conv_request)
                
                tasks = [process_single_conversation(conv) for conv in request.conversations]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process exception results
                processed_results = []
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        conv_id = request.conversations[i].conv_id
                        processed_results.append(ConversationProcessingResponse(
                            conv_id=conv_id,
                            success=False,
                            turns_processed=0,
                            sessions_processed=0,
                            total_memories=0,
                            memory_levels={},
                            processing_time=0.0,
                            user_id="",
                            expert_id="",
                            speakers=[],
                            error=str(result),
                            session_details=[]
                        ))
                    else:
                        processed_results.append(result)
                
                results = processed_results
            else:
                # Sequential processing
                results = []
                for conv_request in request.conversations:
                    result = await self.process_conversation(conv_request)
                    results.append(result)
            
            # Aggregate results
            successful_conversations = sum(1 for r in results if r.success)
            failed_conversations = len(results) - successful_conversations
            total_turns_processed = sum(r.turns_processed for r in results)
            total_memories_generated = sum(r.total_memories for r in results)
            total_processing_time = (datetime.now() - start_time).total_seconds()
            
            # Calculate performance metrics
            performance_metrics = {
                "avg_processing_time_per_conversation": total_processing_time / len(request.conversations),
                "avg_turns_per_conversation": total_turns_processed / len(request.conversations),
                "avg_memories_per_conversation": total_memories_generated / len(request.conversations),
                "success_rate": (successful_conversations / len(request.conversations)) * 100,
                "parallel_processing": request.parallel,
                "max_concurrent": request.max_concurrent
            }
            
            return BatchConversationResponse(
                success=failed_conversations == 0,
                total_conversations=len(request.conversations),
                successful_conversations=successful_conversations,
                failed_conversations=failed_conversations,
                total_turns_processed=total_turns_processed,
                total_memories_generated=total_memories_generated,
                total_processing_time=total_processing_time,
                results=results,
                performance_metrics=performance_metrics
            )
            
        except Exception as e:
            total_processing_time = (datetime.now() - start_time).total_seconds()
            self._logger.error(f"Batch conversation processing failed: {e}")
            
            return BatchConversationResponse(
                success=False,
                total_conversations=len(request.conversations),
                successful_conversations=0,
                failed_conversations=len(request.conversations),
                total_turns_processed=0,
                total_memories_generated=0,
                total_processing_time=total_processing_time,
                results=[],
                performance_metrics={"error": str(e)}
            )
    
    
    def _extract_and_enhance_text_with_image_info(self, dialogue: dict, original_text: str) -> str:
        """Extract image-to-text information from dialogue data and enhance text content"""
        enhanced_text = original_text
        
        # Check if contains image-related information
        img_url = dialogue.get("img_url")
        blip_caption = dialogue.get("blip_caption")
        query = dialogue.get("query")
        
        # If any image-related information exists, enhance
        if img_url or blip_caption or query:
            image_info_parts = []
            
            # Add image description information (BLIP caption)
            if blip_caption:
                image_info_parts.append(f"[Image: {blip_caption}]")
            
            # Add query information (more specific image content)
            if query and query != blip_caption:
                image_info_parts.append(f"[Content: {query}]")
            
            # Concatenate image information to original text
            if image_info_parts:
                image_info = " ".join(image_info_parts)
                enhanced_text = f"{original_text} {image_info}"
        
        return enhanced_text
    
    async def health_check(self) -> ServiceHealthResponse:
        """Perform health check"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        # Check dependency service status
        dependencies = {
            "workflow": self.workflow is not None and hasattr(self.workflow, 'app') and self.workflow.app is not None,
            "storage_manager": self.storage_manager is not None,
            "connection_pool": self.pool_manager is not None and await self.pool_manager.health_check() if self.pool_manager else False
        }
        
        # Update connection pool utilization
        if self.pool_manager:
            metrics = self.pool_manager.get_metrics_summary()
            self.metrics.connection_pool_utilization = metrics.get("utilization_rate", 0.0)
        
        # Update last health check time
        self.metrics.last_health_check = datetime.now()
        
        # Determine service status
        if all(dependencies.values()):
            status = ServiceStatus.READY
        elif any(dependencies.values()):
            status = ServiceStatus.DEGRADED
        else:
            status = ServiceStatus.ERROR
        
        return ServiceHealthResponse(
            status=status,
            uptime=uptime,
            metrics=self.metrics,
            dependencies=dependencies
        )
    
    async def shutdown(self):
        """Shutdown service"""
        if not self._initialized:
            return
            
        self.status = ServiceStatus.SHUTTING_DOWN
        self._logger.info("Starting to shutdown memory generation service...")
        
        try:
            # Wait for active workflows to complete
            if self._active_workflows:
                self._logger.info(f"Waiting for {len(self._active_workflows)} active workflows to complete...")
                await asyncio.gather(*self._active_workflows.values(), return_exceptions=True)
            
            # Cleanup workflow
            if self.workflow:
                await self.workflow.cleanup()
                self.workflow = None
            
            # Cleanup storage manager
            if self.storage_manager:
                if hasattr(self.storage_manager, 'close_all_connections'):
                    await self.storage_manager.close_all_connections()
                self.storage_manager = None
            
            # Cleanup connection pool
            if self.pool_manager:
                await self.pool_manager.cleanup()
                self.pool_manager = None
            
            self._initialized = False
            self.status = ServiceStatus.ERROR
            self._logger.info("Memory generation service shutdown complete")
            
        except Exception as e:
            self._logger.error(f"Error during service shutdown: {e}")
    
    def get_status(self) -> ServiceStatus:
        """Get current service status"""
        return self.status
    
    def get_metrics(self) -> ServiceMetrics:
        """Get current service metrics"""
        return self.metrics


# Global service instance
_memory_generation_service: Optional[MemoryGenerationService] = None
_service_lock = asyncio.Lock()


async def get_memory_generation_service() -> MemoryGenerationService:
    """Get memory generation service singleton instance"""
    global _memory_generation_service
    
    if _memory_generation_service is None:
        async with _service_lock:
            if _memory_generation_service is None:
                _memory_generation_service = MemoryGenerationService()
                await _memory_generation_service.initialize()
    
    return _memory_generation_service


async def cleanup_memory_generation_service():
    """Cleanup and shutdown memory generation service"""
    global _memory_generation_service
    
    if _memory_generation_service is not None:
        await _memory_generation_service.shutdown()
        _memory_generation_service = None


# FastAPI integration
def create_memory_generation_app() -> FastAPI:
    """Create memory generation service FastAPI application"""
    
    app = FastAPI(
        title="TiMem Memory Generation Service",
        description="Memory generation online service based on LangGraph",
        version="1.0.0"
    )
    
    @app.on_event("startup")
    async def startup_event():
        """Application startup event"""
        service = await get_memory_generation_service()
        logger.info("Memory generation service started")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Application shutdown event"""
        await cleanup_memory_generation_service()
        logger.info("Memory generation service shutdown")
    
    @app.post("/generate", response_model=MemoryGenerationResponse)
    async def generate_memory_endpoint(
        request: MemoryGenerationRequest,
        service: MemoryGenerationService = Depends(get_memory_generation_service)
    ):
        """Memory generation endpoint"""
        return await service.generate_memory(request)
    
    @app.get("/health", response_model=ServiceHealthResponse)
    async def health_check_endpoint(
        service: MemoryGenerationService = Depends(get_memory_generation_service)
    ):
        """Health check endpoint"""
        return await service.health_check()
    
    @app.get("/metrics")
    async def metrics_endpoint(
        service: MemoryGenerationService = Depends(get_memory_generation_service)
    ):
        """Metrics endpoint"""
        return service.get_metrics()
    
    return app


# Convenience function
async def generate_memory_sync(
    user_id: str,
    expert_id: str,
    session_id: str,
    content: str,
    timestamp: Optional[datetime] = None,
    metadata: Optional[Dict[str, Any]] = None,
    debug_mode: bool = False
) -> MemoryGenerationResponse:
    """
    Synchronous memory generation interface
    
    Args:
        user_id: User ID
        expert_id: Expert ID
        session_id: Session ID
        content: Dialogue content
        timestamp: Timestamp
        metadata: Metadata
        debug_mode: Debug mode
        
    Returns:
        Memory generation response
    """
    service = await get_memory_generation_service()
    
    request = MemoryGenerationRequest(
        user_id=user_id,
        expert_id=expert_id,
        session_id=session_id,
        content=content,
        timestamp=timestamp or datetime.now(),
        metadata=metadata,
        debug_mode=debug_mode
    )
    
    return await service.generate_memory(request)
