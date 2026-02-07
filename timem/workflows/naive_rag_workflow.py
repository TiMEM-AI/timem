"""
Naive RAG Workflow - Basic RAG implementation for ablation experiments

This is a minimalist RAG implementation for ablation experiment comparison:
- Only uses semantic vector retrieval (Qdrant)
- Fixed return of Top-20 memories
- Does not include: BM25, intelligent routing, hierarchical retrieval, Bottom-up, memory refining and other complex features
- Directly uses LLM to generate answers

Design purpose: Demonstrate the necessity of TiMem's complex retrieval framework
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_app_config
from storage.memory_storage_manager import get_memory_storage_manager_async
from llm.llm_manager import get_llm

logger = get_logger(__name__)


class NaiveRAGWorkflow:
    """
    Naive RAG Workflow class
    
    Minimalist RAG implementation:
    1. Semantic vector retrieval (Qdrant) - Top K (configurable)
    2. LLM generates answers
    """
    
    def __init__(self, 
                 config: Optional[Dict[str, Any]] = None,
                 debug_mode: bool = False,
                 enabled_layers: Optional[List[str]] = None,
                 top_k: int = 20):
        """
        Initialize Naive RAG workflow
        
        Args:
            config: Configuration information
            debug_mode: Whether to enable debug mode
            enabled_layers: Enabled memory layers (e.g. ['L1'] or ['L1', 'L2', 'L3', 'L4', 'L5'])
            top_k: Number of Top-K retrievals (default 20)
        """
        self.config = config or get_app_config()
        self.debug_mode = debug_mode
        self.enabled_layers = enabled_layers or ['L1', 'L2', 'L3', 'L4', 'L5']
        self.top_k = top_k
        
        self.logger = get_logger(__name__)
        
        # Initialize LLM configuration
        answer_gen_config = self.config.get("answer_generation", {}).get("single_cot", {})
        self.llm_provider = answer_gen_config.get("llm_provider", "openai")
        self.llm_model_name = answer_gen_config.get("llm_model", "gpt-4o-mini")
        self.llm_temperature = answer_gen_config.get("temperature", 0.7)
        # Force use of 2048 tokens to ensure answers are not limited (do not use dataset configuration's 512 limit)
        self.llm_max_tokens = 2048
        
        self.logger.info(f"Initialize Naive RAG workflow, debug mode: {self.debug_mode}")
        self.logger.info(f"Enabled memory layers: {self.enabled_layers}")
        
        if self.debug_mode:
            print(f"🔧 Naive RAG workflow initialization")
            print(f"   - Enabled layers: {self.enabled_layers}")
            print(f"   - Top-K: 20")
            print(f"   - Retrieval method: Pure semantic vector retrieval")
    
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run Naive RAG workflow
        
        Args:
            input_data: Input data, must contain question field
            
        Returns:
            Workflow execution result
        """
        start_time = time.time()
        
        try:
            if self.debug_mode:
                print(f"\n🚀 Start executing Naive RAG workflow...")
            
            question = input_data.get("question", "")
            user_id = input_data.get("user_id", "")
            expert_id = input_data.get("expert_id", "")
            user_group_ids = input_data.get("user_group_ids", [])
            
            if not question.strip():
                return self._create_error_response("Question cannot be empty")
            
            self.logger.info(f"Start Naive RAG retrieval: {question}")
            
            # ==================== Step 1: Semantic vector retrieval ====================
            if self.debug_mode:
                print(f"📍 Step 1: Semantic vector retrieval (Top-{self.top_k})")
            
            retrieved_memories = await self._semantic_search(
                question=question,
                user_id=user_id,
                expert_id=expert_id,
                user_group_ids=user_group_ids,
                top_k=self.top_k
            )
            
            self.logger.info(f"Semantic retrieval completed, retrieved {len(retrieved_memories)} memories")
            
            if self.debug_mode:
                print(f"   ✅ Retrieved {len(retrieved_memories)} memories")
                for i, mem in enumerate(retrieved_memories[:3], 1):
                    print(f"      {i}. [{mem.get('level', 'L?')}] {mem.get('content', '')[:60]}...")
            
            # ==================== Step 2: LLM generates answer ====================
            if self.debug_mode:
                print(f"📍 Step 2: LLM generates answer")
            
            # Check if only returning memories
            return_memories_only = input_data.get("return_memories_only", False)
            
            if return_memories_only:
                answer = ""
                confidence = 0.0
                self.logger.info("Memory-only return mode, skip LLM generation")
                if self.debug_mode:
                    print(f"   ⚠️ Memory-only return mode, skip LLM generation")
            else:
                answer, confidence = await self._generate_answer(
                    question=question,
                    memories=retrieved_memories,
                    input_data=input_data  # Pass input_data to get question_date
                )
                self.logger.info(f"Answer generation completed, confidence: {confidence:.3f}")
                if self.debug_mode:
                    print(f"   ✅ Answer generation completed")
                    print(f"      Confidence: {confidence:.3f}")
                    print(f"      Answer length: {len(answer)} characters")
            
            # ==================== Build response ====================
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Format memories for diagnostic output
            formatted_memories = self._format_memories_for_display(retrieved_memories)
            
            response = {
                "question": question,
                "answer": answer,
                "confidence": confidence,
                "evidence": [],
                "formatted_context_memories": formatted_memories,
                "retrieval_metadata": {
                    "retrieval_time": execution_time,
                    "total_memories_searched": len(retrieved_memories),
                    "strategies_used": ["naive_rag_semantic"],
                    "strategy_performance": {},
                    "query_category": "NAIVE_RAG",
                    "query_complexity": None,
                    "retrieval_strategy": "naive_rag",
                    "retrieval_description": f"Naive RAG: Semantic retrieval Top-20 (layers: {','.join(self.enabled_layers)})",
                    "llm_keywords": [],
                    "enabled_layers": self.enabled_layers
                },
                "reflection_info": {
                    "reflection_count": 0,
                    "reflection_history": [],
                    "original_question": question,
                    "l1_expansion_multiplier": 1
                },
                "retrieved_memories": retrieved_memories,
                "thinking_events": [],
                "errors": [],
                "warnings": [],
                "use_multi_stage_cot": False,
                "use_single_cot": False,
                "execution_stats": {
                    "start_time": start_time,
                    "end_time": end_time,
                    "execution_time": execution_time,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            if self.debug_mode:
                print(f"\n✅ Naive RAG workflow execution completed")
                print(f"⏱️ Execution time: {execution_time:.2f} seconds")
                print(f"📚 Retrieved memories: {len(retrieved_memories)} items")
            
            self.logger.info(f"Naive RAG workflow execution completed, elapsed time: {execution_time:.2f}s")
            return response
            
        except Exception as e:
            self.logger.error(f"Naive RAG workflow execution failed: {str(e)}", exc_info=True)
            return self._create_error_response(f"Execution failed: {str(e)}")
    
    async def _semantic_search(self, 
                               question: str, 
                               user_id: str,
                               expert_id: str,
                               user_group_ids: List[str],
                               top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Semantic vector retrieval
        
        Args:
            question: Query question
            user_id: User ID
            expert_id: Expert ID
            user_group_ids: List of user group IDs
            top_k: Return Top-K results
            
        Returns:
            List of retrieved memories
        """
        try:
            storage_manager = await get_memory_storage_manager_async()
            
            # Build query
            query = {"query_text": question}
            
            # User group filtering (if provided)
            if user_group_ids and len(user_group_ids) >= 2:
                query["user_group_ids"] = user_group_ids
                self.logger.info(f"🔒 Naive RAG enables user group isolation: {user_group_ids}")
            else:
                # User/expert filtering
                if user_id:
                    query["user_id"] = user_id
                if expert_id:
                    query["expert_id"] = expert_id
            
            # Build filter conditions (layer filtering)
            filter_conditions = {}
            if self.enabled_layers:
                filter_conditions["level"] = self.enabled_layers
                self.logger.info(f"🔍 Naive RAG layer filtering: {self.enabled_layers}")
            
            # Build options
            options = {
                "limit": top_k,
                "score_threshold": 0.0,
                "sort_by": "relevance",
                "filter": filter_conditions
            }
            
            self.logger.info(f"Execute Naive RAG semantic retrieval, question: {question[:50]}...")
            
            # Execute semantic retrieval
            all_results = await storage_manager.search_memories(query, options, storage_type="vector")
            
            # Format results
            memories = []
            for result in all_results:
                if hasattr(result, 'to_dict'):
                    result_dict = result.to_dict()
                elif isinstance(result, dict):
                    result_dict = result.copy()
                else:
                    result_dict = {"content": str(result)}
                
                # Extract score
                semantic_score = result_dict.get("vector_score", result_dict.get("retrieval_score", 0.0))
                
                memory = {
                    "id": result_dict.get("id"),
                    "content": result_dict.get("content", ""),
                    "level": result_dict.get("level", "L1"),
                    "session_id": result_dict.get("session_id"),
                    "created_at": result_dict.get("created_at"),
                    "metadata": result_dict.get("metadata", {}),
                    "score": semantic_score,
                    "retrieval_method": "naive_rag_semantic",
                    "retrieval_source": "naive_rag"
                }
                memories.append(memory)
            
            self.logger.info(f"Naive RAG semantic retrieval completed: {len(memories)} memories")
            return memories
            
        except Exception as e:
            self.logger.error(f"Naive RAG semantic retrieval failed: {str(e)}", exc_info=True)
            return []
    
    async def _generate_answer(self, 
                               question: str, 
                               memories: List[Dict[str, Any]],
                               input_data: Optional[Dict[str, Any]] = None) -> tuple[str, float]:
        """
        Use LLM to generate answer
        
        Args:
            question: User question
            memories: List of retrieved memories
            input_data: Input data (for getting question_date and other additional information)
            
        Returns:
            (answer, confidence)
        """
        try:
            # Get LLM manager
            llm_manager = get_llm()
            
            # Build context (Naive RAG - simplified format: only keep timestamps)
            # Do not add sequence numbers, do not add layer labels, do not reorder, but keep timestamps
            context_parts = []
            for mem in memories:
                content = mem.get('content', '').strip()
                if not content:
                    continue
                
                # Extract and format timestamp
                timestamp = mem.get('created_at', mem.get('time_window_start', ''))
                if timestamp:
                    try:
                        if 'T' in timestamp:
                            date_str = timestamp.split('T')[0]
                        else:
                            date_str = timestamp[:10]
                        from datetime import datetime as dt
                        date_obj = dt.strptime(date_str, '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%d %b %Y')
                        memory_text = f"[{formatted_date}] {content}"
                    except:
                        memory_text = content
                else:
                    memory_text = content
                
                context_parts.append(memory_text)
            
            context = "\n\n".join(context_parts) if context_parts else "No relevant memories"
            
            # Build prompt (load from dataset configuration, support COT)
            from timem.utils.config_manager import get_config
            
            # Load dataset-specific qa_prompts configuration (will automatically load longmemeval_s configuration)
            qa_prompts = get_config("qa_prompts")
            
            # Check if COT is enabled (consistent with baseline)
            enable_cot = qa_prompts.get("ENABLE_COT", False)
            
            # Select template: if COT is enabled, use LongMemEval COT template; otherwise use MEM0 template
            if enable_cot:
                prompt_key = "ANSWER_PROMPT_LONGMEMEVAL_COT"
                self.logger.info("✅ Naive RAG enables COT reasoning mode (using LongMemEval COT template)")
            else:
                prompt_key = "ANSWER_PROMPT_MEM_0"
                self.logger.info("Use standard answer generation mode (MEM0 template)")
            
            # Get template
            prompt_template = qa_prompts.get(prompt_key, {})
            
            # Prefer English template, use Chinese if not available
            template_text = prompt_template.get('en', prompt_template.get('zh', ''))
            
            if not template_text:
                self.logger.warning(f"Template {prompt_key} not found, using default template")
                template_text = """You are an intelligent memory assistant tasked with retrieving accurate information from conversation memories.

# CONTEXT:
You have access to memories from two speakers in a conversation. These memories contain
timestamped information that may be relevant to answering the question.

# INSTRUCTIONS:
1. Carefully analyze all provided memories from both speakers
2. Pay special attention to the timestamps to determine the answer
3. If the question asks about a specific event or fact, look for direct evidence in the memories
4. If the memories contain contradictory information, prioritize the most recent memory
5. If there is a question about time references (like "last year", "two months ago", etc.),
   calculate the actual date based on the memory timestamp. For example, if a memory from
   4 May 2022 mentions "went to India last year," then the trip occurred in 2021.
6. Always convert relative time references to specific dates, months, or years. For example,
   convert "last year" to "2022" or "two months ago" to "March 2023" based on the memory
   timestamp. Ignore the reference while answering the question.
7. Focus only on the content of the memories from both speakers. Do not confuse character
   names mentioned in memories with the actual users who created those memories.
8. The answer should be less than 5-6 words.

# APPROACH (Think step by step):
1. First, examine all memories that contain information related to the question
2. Examine the timestamps and content of these memories carefully
3. Look for explicit mentions of dates, times, locations, or events that answer the question
4. If the answer requires calculation (e.g., converting relative time references), show your work
5. Formulate a precise, concise answer based solely on the evidence in the memories
6. Double-check that your answer directly addresses the question asked
7. Ensure your final answer is specific and avoids vague time references

Relevant Memories:
{context_memories}

Question: {question}

Answer:"""
            
            # Format prompt (LongMemEval template needs 3 parameters: memories, date, question)
            # Try to detect template format: positional arguments {} or named arguments {name}
            if "{}" in template_text:
                # LongMemEval style: positional argument format
                # Extract question date (from input data or use current date)
                question_date = ""
                if input_data:
                    question_date = input_data.get("question_date", "")
                if not question_date:
                    # Try to extract date from latest timestamp in memories
                    if memories:
                        latest_memory = max(memories, key=lambda m: m.get('created_at', ''))
                        timestamp = latest_memory.get('created_at', '')
                        if timestamp:
                            try:
                                if 'T' in timestamp:
                                    question_date = timestamp.split('T')[0]
                                else:
                                    question_date = timestamp[:10]
                            except:
                                question_date = "Unknown"
                    else:
                        question_date = "Unknown"
                
                prompt = template_text.format(
                    context,  # First parameter: memory content
                    question_date,  # Second parameter: question date
                    question  # Third parameter: question
                )
                self.logger.info(f"✅ Using LongMemEval template (positional arguments), question date: {question_date}")
            else:
                # TiMem style: named argument format
                prompt = template_text.format(
                    context_memories=context,
                    question=question
                )
                self.logger.info("Using TiMem template (named arguments)")
            
            # Format as messages format (LLM manager will automatically record prompt)
            messages = llm_manager.format_chat_prompt("", prompt)
            
            # Call LLM
            response = await llm_manager.chat(
                messages,
                model=self.llm_model_name,
                temperature=self.llm_temperature,
                max_tokens=self.llm_max_tokens
            )
            
            # Extract answer
            answer = response.content if response.content else "Sorry, unable to generate answer."
            
            # Simple confidence calculation (based on memory count and average score)
            if memories:
                avg_score = sum(m.get("score", 0.0) for m in memories) / len(memories)
                memory_factor = min(len(memories) / 20, 1.0)  # Memory count factor
                confidence = (avg_score * 0.7 + memory_factor * 0.3)
            else:
                confidence = 0.0
            
            self.logger.info(f"✅ Naive RAG answer generation successful, answer length: {len(answer)}")
            return answer, confidence
            
        except Exception as e:
            self.logger.error(f"Answer generation failed: {str(e)}", exc_info=True)
            return "Sorry, answer generation failed.", 0.0
    
    def _format_memories_for_display(self, memories: List[Dict[str, Any]]) -> List[str]:
        """
        Format memories for diagnostic output (Naive RAG - simplified format)
        
        Naive RAG simplification principles:
        - Do not group by layer
        - Do not add layer titles (e.g. "[Related Memory Fragments]")
        - Do not reorder (keep retrieval order)
        - Keep timestamps (basic time information)
        
        Args:
            memories: List of retrieved memories
            
        Returns:
            List of formatted memory texts (simplified format with timestamps)
        """
        if not memories:
            return []
        
        formatted = []
        
        # Naive RAG: Simplified format, add timestamps but do not reorder or group
        for mem in memories:
            content = mem.get('content', '').strip()
            if not content:
                continue
            
            # Extract timestamp
            timestamp = mem.get('created_at', mem.get('time_window_start', ''))
            
            if timestamp:
                # Extract and format date
                try:
                    if 'T' in timestamp:
                        date_str = timestamp.split('T')[0]
                    else:
                        date_str = timestamp[:10]
                    # Format as [DD MMM YYYY] format
                    from datetime import datetime as dt
                    date_obj = dt.strptime(date_str, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d %b %Y')
                    memory_text = f"[{formatted_date}] {content}"
                except:
                    # If timestamp parsing fails, keep only content
                    memory_text = content
            else:
                memory_text = content
            
            formatted.append(memory_text)
        
        return formatted
    
    def _create_error_response(self, error_msg: str) -> Dict[str, Any]:
        """Create error response"""
        return {
            "question": "",
            "answer": "",
            "confidence": 0.0,
            "evidence": [],
            "formatted_context_memories": [],
            "retrieval_metadata": {
                "retrieval_time": 0.0,
                "total_memories_searched": 0,
                "strategies_used": [],
                "strategy_performance": {},
                "query_category": "NAIVE_RAG",
                "retrieval_strategy": "naive_rag",
                "enabled_layers": self.enabled_layers
            },
            "retrieved_memories": [],
            "errors": [error_msg],
            "warnings": [],
            "success": False,
            "timestamp": datetime.now().isoformat()
        }
    
    async def cleanup(self):
        """Clean up resources (Naive RAG does not need cleanup)"""
        pass


async def run_naive_rag(input_data: Dict[str, Any], 
                        debug_mode: bool = False,
                        enabled_layers: Optional[List[str]] = None,
                        top_k: int = 20) -> Dict[str, Any]:
    """
    Main function to run Naive RAG workflow
    
    Args:
        input_data: Input data, must contain question field
        debug_mode: Whether to enable debug mode
        enabled_layers: Enabled memory layers
        top_k: Number of Top-K retrievals (default 20)
        
    Returns:
        Workflow execution result
    """
    workflow = NaiveRAGWorkflow(
        debug_mode=debug_mode,
        enabled_layers=enabled_layers,
        top_k=top_k
    )
    return await workflow.run(input_data)

