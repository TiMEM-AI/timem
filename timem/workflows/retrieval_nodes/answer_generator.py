"""
Answer Generation Node

Responsible for generating high-quality answers based on retrieved memories, including confidence assessment.
Supports time-aware memory formatting and QA prompts.
"""

from typing import Dict, List, Any, Optional
import re

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator
from timem.workflows.nodes.memory_time_sorter import MemoryTimeSorter
from llm.llm_manager import get_llm
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_config
from timem.utils.time_formatter import get_time_formatter

logger = get_logger(__name__)


class AnswerGenerator:
    """Answer generation node"""
    
    def __init__(self, 
                 llm_manager: Optional[Any] = None,
                 state_validator: Optional[RetrievalStateValidator] = None,
                 time_sorter: Optional[MemoryTimeSorter] = None):
        """
        Initialize answer generator
        
        Args:
            llm_manager: LLM manager, auto-fetch if None
            state_validator: State validator, create new instance if None
            time_sorter: Time sorter, create new instance if None
        """
        self.llm_manager = llm_manager
        self.state_validator = state_validator or RetrievalStateValidator()
        self.time_sorter = time_sorter or MemoryTimeSorter()
        
        # Unified time formatter
        self.time_formatter = get_time_formatter()
        
        self.logger = get_logger(__name__)
        
        # Answer generation configuration
        self.max_context_memories = 5  # Max 5 memories as context
        self.min_confidence_threshold = 0.1  # Minimum confidence threshold
        
        # Load configuration
        self.qa_prompts = get_config("qa_prompts")
        
        # 🔧 Load QA LLM model configuration (from dataset config)
        self.qa_llm_config = self.qa_prompts.get("qa_llm_config", {})
        self.qa_model = self.qa_llm_config.get("model", "gpt-4o-mini")  # Default: gpt-4o-mini
        self.qa_temperature = self.qa_llm_config.get("temperature", 0.7)
        self.qa_max_tokens = self.qa_llm_config.get("max_tokens", 512)
        
        # Get global language configuration
        self.global_language = self._get_global_language()
        self.logger.info(f"Answer generator initialized, global language: {self.global_language}, QA model: {self.qa_model}")
    
    def _get_global_language(self) -> str:
        """Get global language configuration"""
        try:
            app_config = get_config("app")
            language = app_config.get("language", "en")
            return language.lower()
        except Exception as e:
            self.logger.warning(f"Failed to get global language config: {e}, using default 'en'")
            return "en"
        
    async def _get_llm_manager(self):
        """Get LLM manager instance"""
        if self.llm_manager is None:
            self.llm_manager = get_llm()
        return self.llm_manager
        
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run answer generation
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            # ✅ Use unified configuration check function
            from timem.workflows.retrieval_config import should_skip_llm_generation, get_retrieval_mode_description
            
            if should_skip_llm_generation(state):
                return_memories_only = state.get("return_memories_only", False)
                mode_desc = get_retrieval_mode_description(return_memories_only)
                
                self.logger.info("✨ ============ Memory-only return mode ============")
                self.logger.info(f"✨ Retrieval mode: {mode_desc}")
                self.logger.info(f"✨ return_memories_only: {return_memories_only}")
                self.logger.info(f"✨ Directly return {len(retrieval_state.ranked_results)} retrieved memories without LLM call")
                
                # ✨ Send thinking event: skip LLM generation
                from app.schemas.dialogue import SSEThinkingEvent, ThinkingStep, ThinkingStepType, RetrievedMemoryDetail
                from datetime import datetime
                
                # Build retrieved memory details
                retrieved_memories_details = []
                for memory in retrieval_state.ranked_results:
                    # ✨ Handle timestamp: ensure string format
                    timestamp_value = memory.get('created_at') or memory.get('timestamp')
                    if timestamp_value:
                        from datetime import datetime
                        if isinstance(timestamp_value, datetime):
                            timestamp_str = timestamp_value.isoformat()
                        else:
                            timestamp_str = str(timestamp_value)
                    else:
                        timestamp_str = None
                    
                    # ✨ Extract session_id: prioritize top-level field, then metadata
                    session_id = memory.get('session_id')
                    if not session_id and isinstance(memory.get('metadata'), dict):
                        session_id = memory.get('metadata', {}).get('session_id')
                    
                    # ✨ Calculate composite score: prioritize fused_score, ensure None becomes 0.0
                    score = memory.get('fused_score') or memory.get('final_ranking_score') or memory.get('score') or memory.get('retrieval_score') or 0.0
                    
                    memory_detail = RetrievedMemoryDetail(
                        memory_id=memory.get('id') or memory.get('memory_id') or 'unknown',  # ✨ Multi-field compatible
                        content=memory.get('content', ''),
                        level=memory.get('level', 'L1'),
                        score=float(score),  # ✨ Ensure float type
                        session_id=session_id,  # ✨ Use extracted session_id
                        timestamp=timestamp_str,  # ✨ Ensure string
                        metadata=memory.get('metadata', {})
                    )
                    retrieved_memories_details.append(memory_detail)
                
                # Send thinking event for skipping LLM generation
                thinking_event = SSEThinkingEvent(
                    step=ThinkingStep(
                        step_type=ThinkingStepType.MEMORY_INTEGRATION,  # Use memory integration step
                        step_name="Skip LLM generation",
                        description=f"Directly return {len(retrieval_state.ranked_results)} retrieved memories without LLM answer generation",
                        status="completed",
                        progress=1.0,
                        data={
                            "skipped_llm": True,
                            "memories_count": len(retrieval_state.ranked_results),
                            "return_memories_only": True
                        }
                    ),
                    retrieved_memories=retrieved_memories_details,
                    timestamp=datetime.now().isoformat()
                )
                
                # Add thinking event to state for upper-level processing
                state["thinking_event"] = thinking_event
                
                # Directly return retrieval results without generating answer
                retrieval_state.answer = ""  # No answer generation
                retrieval_state.confidence = 1.0  # Confidence of memories themselves
                retrieval_state.evidence = [
                    {
                        "memory_id": mem.get("id"),
                        "content": mem.get("content", ""),
                        "level": mem.get("level", ""),
                        "score": mem.get("score", 0.0)
                    }
                    for mem in retrieval_state.ranked_results[:5]  # Return max 5
                ]
                
                self.logger.info("✨ ============ Skip LLM generation complete ============")
                return self._state_to_dict(retrieval_state)
            
            self.logger.info("📝 ============ Start LLM answer generation ============")
            
            # Check if retrieval results exist
            if not retrieval_state.ranked_results:
                self.logger.warning("No retrieval results, generating default answer")
                retrieval_state.answer = "Sorry, I couldn't find relevant memory information to answer your question."
                retrieval_state.confidence = 0.0
                retrieval_state.evidence = []
                return self._state_to_dict(retrieval_state)
            
            # Step 1: Build context
            context_memories = self._build_context(retrieval_state)
            
            # Step 2: Generate prompt
            prompt = self._build_answer_prompt(retrieval_state, context_memories)
            
            # Step 3: Call LLM to generate answer
            answer = await self._generate_answer_with_llm(prompt)
            
            # Step 4: Check if reflection is needed (optimize question and re-retrieve)
            reflection_info = self._extract_reflection_info(answer)
            if reflection_info and self._should_trigger_reflection(state):
                self.logger.info("🤔 Detected reflection need, preparing to optimize question and re-retrieve")
                # Set reflection flag and optimized question
                retrieval_state.needs_reflection = True
                retrieval_state.optimized_question = reflection_info.get("optimized_question", "")
                retrieval_state.reflection_reason = reflection_info.get("reason", "")
                retrieval_state.original_answer = answer  # Save original answer
                
                # Temporarily set low confidence, wait for reflection completion
                retrieval_state.answer = "Performing reflection retrieval, please wait..."
                retrieval_state.confidence = 0.1
                retrieval_state.evidence = []
                confidence = 0.1  # Set confidence variable for logging
                
                self.logger.info(f"Optimized question: {retrieval_state.optimized_question}")
                self.logger.info(f"Reflection reason: {retrieval_state.reflection_reason}")
                
            else:
                # Step 5: Calculate confidence
                confidence = self._calculate_answer_confidence(retrieval_state, answer)
                
                # Step 6: Extract evidence
                evidence = self._extract_evidence(retrieval_state)
                
                # Step 7: Update state
                retrieval_state.answer = answer
                retrieval_state.confidence = confidence
                retrieval_state.evidence = evidence
            
            # Save formatted memory content to state (for test reports)
            retrieval_state.formatted_context_memories = context_memories
            
            # Step 8: Validate final output
            errors = self.state_validator.validate_final_output(retrieval_state)
            if errors:
                retrieval_state.errors.extend(errors)
            
            self.logger.info(f"Answer generation complete: confidence {confidence:.3f}")
            
            # 🔧 Engineering-level fix: preserve all fields from original state (especially ablation study memory refiner fields)
            result_state = self._state_to_dict(retrieval_state)
            
            # Merge fields from original state not in RetrievalState (e.g., memory_refiner_enabled)
            for key in state:
                if key not in result_state:
                    result_state[key] = state[key]
            
            return result_state
            
        except Exception as e:
            error_msg = f"Answer generation failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            
            # Set fallback answer
            state["answer"] = "Sorry, an error occurred during answer generation."
            state["confidence"] = 0.0
            state["evidence"] = []
            
            return state
    
    def update_language_config(self, new_language: str):
        """Update language configuration"""
        if new_language.lower() in ["zh", "en"]:
            self.global_language = new_language.lower()
            self.logger.info(f"Language config updated to: {self.global_language}")
        else:
            self.logger.warning(f"Invalid language config: {new_language}, keeping current: {self.global_language}")
    
    def get_current_language(self) -> str:
        """Get current language configuration"""
        return self.global_language
    
    def _extract_reflection_info(self, answer: str) -> Optional[Dict[str, str]]:
        """
        Extract reflection info (optimized question) from LLM answer
        
        Args:
            answer: LLM-generated answer
            
        Returns:
            Dictionary with optimized_question and reason, None if no reflection needed
        """
        try:
            import json
            import re
            
            self.logger.debug(f"Start extracting reflection info, answer length: {len(answer)}")
            
            # Multiple JSON matching patterns for better error handling
            json_patterns = [
                # Standard JSON format
                r'\{[^{}]*"optimized_question"[^{}]*\}',
                # JSON format allowing line breaks
                r'\{[^{}]*"optimized_question"[^{}]*\}',
                # Loose matching allowing more nesting
                r'\{(?:[^{}]|{[^{}]*})*"optimized_question"(?:[^{}]|{[^{}]*})*\}'
            ]
            
            for pattern in json_patterns:
                json_matches = re.findall(pattern, answer, re.DOTALL | re.MULTILINE)
                self.logger.debug(f"Using pattern {pattern} found {len(json_matches)} matches")
                
                for i, json_str in enumerate(json_matches):
                    try:
                        # Clean JSON string
                        cleaned_json = json_str.strip()
                        self.logger.debug(f"Attempting to parse JSON #{i+1}: {cleaned_json[:100]}...")
                        
                        # Parse JSON
                        reflection_data = json.loads(cleaned_json)
                        
                        if "optimized_question" in reflection_data:
                            optimized_question = reflection_data.get("optimized_question", "").strip()
                            reason = reflection_data.get("reason", "Need more specific information").strip()
                            
                            if optimized_question:
                                self.logger.info(f"✅ Successfully extracted reflection info:")
                                self.logger.info(f"   Optimized question: {optimized_question}")
                                self.logger.info(f"   Reflection reason: {reason}")
                                return {
                                    "optimized_question": optimized_question,
                                    "reason": reason
                                }
                        else:
                            self.logger.debug(f"Missing optimized_question field in JSON: {reflection_data}")
                            
                    except json.JSONDecodeError as e:
                        self.logger.debug(f"JSON parse failed #{i+1}: {e}")
                        self.logger.debug(f"Problem JSON content: {json_str[:200]}")
                        continue
                    except Exception as e:
                        self.logger.debug(f"Error processing JSON #{i+1}: {e}")
                        continue
            
            # If no valid JSON found, try simple text matching
            self.logger.debug("No valid JSON found, trying text pattern matching")
            
            # Find possible optimized question text
            question_patterns = [
                r'optimized question[：:]\s*"([^"]+)"',
                r'optimized_question[：:]\s*"([^"]+)"',
                r'more targeted question[：:]\s*"([^"]+)"'
            ]
            
            for pattern in question_patterns:
                matches = re.findall(pattern, answer, re.IGNORECASE)
                if matches:
                    optimized_question = matches[0].strip()
                    if optimized_question:
                        self.logger.info(f"✅ Extracted reflection info via text matching: {optimized_question}")
                        return {
                            "optimized_question": optimized_question,
                            "reason": "Extracted via text pattern matching"
                        }
            
            self.logger.debug("No reflection info found")
            return None
            
        except Exception as e:
            self.logger.warning(f"Exception occurred while extracting reflection info: {e}")
            import traceback
            self.logger.debug(f"Exception traceback: {traceback.format_exc()}")
            return None
    
    def _should_trigger_reflection(self, state: Dict[str, Any]) -> bool:
        """
        Determine whether to trigger reflection mechanism
        
        Args:
            state: Workflow state
            
        Returns:
            Whether to trigger reflection
        """
        # Check reflection count limit
        reflection_count = state.get("reflection_count", 0)
        max_reflections = state.get("max_reflections", 3)
        
        if reflection_count >= max_reflections:
            self.logger.info(f"Reached max reflection limit ({max_reflections})")
            return False
        
        # Check if in reflection mode
        if state.get("in_reflection_mode", False):
            self.logger.info("Currently in reflection mode, not triggering new reflection")
            return False
        
        return True
    
    def _build_context(self, state: RetrievalState) -> List[str]:
        """Build context memories with time info, support full L1-L5 level classification"""
        context_memories = []
        
        # Get all sorted results
        all_memories = state.ranked_results
        
        # Group memories by level
        memory_levels = {
            "L1": [],
            "L2": [],
            "L3": [],
            "L4": [],
            "L5": []
        }
        
        # Group memories to corresponding levels
        for memory in all_memories:
            level = memory.get("level", "").upper()
            if level in memory_levels:
                memory_levels[level].append(memory)
            else:
                # Unknown level goes to L1
                memory_levels["L1"].append(memory)
        
        # Process each level in order: L1 → L2 → L3 → L4 → L5
        level_configs = {
            "L1": {
                "zh": "[Related Memory Fragments]",
                "en": "[Related Memory Fragments]",
                "description": "Fragment memory"
            },
            "L2": {
                "zh": "[Related Session Memories]", 
                "en": "[Related Session Memories]",
                "description": "Session memory"
            },
            "L3": {
                "zh": "[Related Daily Report Memories]",
                "en": "[Related Daily Report Memories]", 
                "description": "Daily report memory"
            },
            "L4": {
                "zh": "[Related Weekly Report Memories]",
                "en": "[Related Weekly Report Memories]",
                "description": "Weekly report memory"
            },
            "L5": {
                "zh": "[Related Deep Profile Memories]",
                "en": "[Related Deep Profile Memories]",
                "description": "Deep profile"
            }
        }
        
        # Statistics
        level_counts = {}
        
        # Process each level in order
        for level in ["L1", "L2", "L3", "L4", "L5"]:
            memories = memory_levels[level]
            if not memories:
                continue
                
            level_counts[level] = len(memories)
            config = level_configs[level]
            
            # Add level title
            title = config["zh"] if self.global_language == "zh" else config["en"]
            context_memories.append(title)
            
            # Sort and format memories for this level by time
            formatted_memories = self._format_memories_by_time(memories, level)
            context_memories.extend(formatted_memories)
            
            # Add separator between levels (except last level)
            if level != "L5" and any(memory_levels[next_level] for next_level in ["L1", "L2", "L3", "L4", "L5"][["L1", "L2", "L3", "L4", "L5"].index(level)+1:]):
                context_memories.append("")  # Empty line separator
        
        # Log statistics
        total_memories = sum(level_counts.values())
        level_summary = ", ".join([f"{level}={count}" for level, count in level_counts.items()])
        self.logger.info(f"Built hierarchical context: {level_summary}, total={total_memories}")
        
        return context_memories
    
    def _format_memories_by_time(self, memories: List[Dict[str, Any]], level: str = "L1") -> List[str]:
        """Sort and format memories by time"""
        formatted_memories = []
        
        # Check if time info exists and sort
        memories_with_time = []
        for memory in memories:
            # Extract time info (multiple possible time fields)
            time_info = self._extract_time_info(memory)
            memories_with_time.append({
                'memory': memory,
                'time_info': time_info
            })
        
        # Sort by time (if time info exists)
        if any(item['time_info'] for item in memories_with_time):
            try:
                # Use time sorter to sort
                sorted_memories = self.time_sorter.sort_child_memories(
                    [item['memory'] for item in memories_with_time],
                    sort_order="asc"  # Sort ascending (early to late)
                )
                self.logger.debug("Memories sorted by time")
            except Exception as e:
                self.logger.warning(f"Time sorting failed, using original order: {e}")
                sorted_memories = memories
        else:
            sorted_memories = memories
        
        # Format memory text
        for memory in sorted_memories:
            content = memory.get('content', '')
            
            # Clean memory content
            cleaned_content = self._clean_memory_content(content)
            
            if not cleaned_content.strip():
                continue  # Skip empty content
            
            # Extract and format time info
            time_info = self._extract_time_info(memory)
            time_str = self._format_time_info(time_info) if time_info else ""
            
            # Build memory text format based on level and language config
            if time_str:
                memory_text = self._format_memory_with_time_and_level(time_str, cleaned_content, level)
            else:
                memory_text = self._format_memory_without_time_and_level(cleaned_content, level)
            
            formatted_memories.append(memory_text)
        
        return formatted_memories
    
    def _format_memory_with_time_and_level(self, time_str: str, content: str, level: str) -> str:
        """Format memory with time based on level and language config"""
        if self.global_language == "zh":
            # Chinese format: [time][level] memory content
            return f"[{time_str}] {content}"
        else:
            # English format: [time][level] memory content
            formatted_time = self._convert_to_english_date_format(time_str)
            return f"[{formatted_time}] {content}"
    
    def _format_memory_without_time_and_level(self, content: str, level: str) -> str:
        """Format memory without time based on level and language config"""
        if self.global_language == "zh":
            return f"[Unknown Time] {content}"
        else:
            return f"[Unknown Time] {content}"
    
    def _format_memory_with_time(self, time_str: str, content: str) -> str:
        """Format memory with time based on global language config"""
        if self.global_language == "zh":
            # Chinese format: [2023-08-17]memory content
            return f"[{time_str}]{content}"
        else:
            # English format: [9 June 2023]memory content
            formatted_time = self._convert_to_english_date_format(time_str)
            return f"[{formatted_time}]{content}"
    
    def _format_memory_without_time(self, content: str) -> str:
        """Format memory without time based on global language config"""
        if self.global_language == "zh":
            return f"[Unknown Time]{content}"
        else:
            return f"[Unknown Time]{content}"
    
    def _clean_memory_content(self, content: str) -> str:
        """Clean memory content to ensure LLM input is clean"""
        if not content:
            return ""
        
        # Remove extra whitespace and line breaks
        cleaned = re.sub(r'\s+', ' ', content.strip())
        
        # Remove special control characters
        cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned)
        
        # Remove duplicate punctuation
        cleaned = re.sub(r'([.!?])\1+', r'\1', cleaned)
        
        # Remove extra quotes and parentheses
        cleaned = re.sub(r'["\'\`]+', '"', cleaned)
        cleaned = re.sub(r'\s*["\'\`]\s*$', '', cleaned)  # Remove trailing quotes
        cleaned = re.sub(r'^\s*["\'\`]\s*', '', cleaned)  # Remove leading quotes
        
        # Ensure sentence ends with appropriate punctuation
        if cleaned and not cleaned[-1] in '.!?。！？':
            cleaned += '.'
        
        return cleaned.strip()
    
    def _extract_time_info(self, memory: Dict[str, Any]) -> Optional[str]:
        """Extract time info from memory"""
        # Check multiple possible time fields
        time_fields = [
            'created_at', 'updated_at', 'timestamp', 
            'time_window_start', 'time_window_end',
            'start_time', 'end_time'
        ]
        
        for field in time_fields:
            if field in memory and memory[field]:
                return memory[field]
        
        return None
    
    def _format_time_info(self, time_info: str) -> str:
        """Format time info to concise date format - using unified time formatter"""
        if not time_info:
            return ""
        
        # Use unified time formatter
        return self.time_formatter.format_time_for_display(time_info)
    
    def _convert_to_english_date_format(self, date_str: str) -> str:
        """Convert YYYY-MM-DD format to English date format (e.g., 9 June 2023)"""
        if not date_str or "-" not in date_str:
            return date_str
        
        try:
            from datetime import datetime
            
            # Parse date
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            
            # English month names
            month_names = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ]
            
            # Get month name (index starts from 0)
            month_name = month_names[dt.month - 1]
            
            # Format: 9 June 2023
            return f"{dt.day} {month_name} {dt.year}"
            
        except Exception as e:
            self.logger.warning(f"Failed to convert to English date format: {e}, using original: {date_str}")
            return date_str
    
    def _build_answer_prompt(self, state: RetrievalState, context_memories: List[str]) -> str:
        """Build answer generation prompt"""
        # Prioritize global language config, detect query language if not set
        if self.global_language in ["zh", "en"]:
            language = self.global_language
            is_chinese = (language == "zh")  # Ensure is_chinese is always defined
        else:
            # Fallback to detect query language
            is_chinese = bool(re.search(r'[\u4e00-\u9fff]', state.question))
            language = "zh" if is_chinese else "en"
            self.logger.info(f"Using query language detection result: {language}")
        
        self.logger.info(f"Building prompt using language: {language} (global config: {self.global_language})")
        
        # 🔧 Select prompt template based on config
        # Check ENABLE_COT config in qa_prompts
        enable_cot = self.qa_prompts.get("ENABLE_COT", False)
        
        # Check if current dataset is LongMemEval
        import os
        current_dataset = os.getenv("TIMEM_DATASET_PROFILE", "default")
        is_longmemeval = current_dataset in ["longmemeval_s", "longmemeval_m"]
        
        # Select template
        if enable_cot:
            if is_longmemeval:
                # Use LongMemEval COT template
                prompt_key = "ANSWER_PROMPT_LONGMEMEVAL_COT"
                self.logger.info("✅ Enable COT reasoning mode (LongMemEval)")
            else:
                # Use TiMem default template
                prompt_key = "ANSWER_PROMPT_MEM_0"
                self.logger.info("✅ Enable COT reasoning mode (TiMem)")
        else:
            if is_longmemeval:
                # Use LongMemEval no-COT template
                prompt_key = "ANSWER_PROMPT_LONGMEMEVAL_NO_COT"
                self.logger.info("Using LongMemEval no-COT mode")
            else:
                # Use TiMem default template
                prompt_key = "ANSWER_PROMPT_MEM_0"
                self.logger.info("Using standard answer generation mode")
        
        # Retain original detection logic for debug logging (but doesn't affect template selection)
        time_keywords = ['when', 'what time', 'date', 'what time', 'time', 'date', 'year', 'month', 'day']
        is_time_query = any(keyword.lower() in state.question.lower() for keyword in time_keywords)
        has_time_info = (not is_time_query and 
                        any("time:" in memory.lower() or "Time:" in memory for memory in context_memories))
        
        # Debug logging: show template selection process
        self.logger.info(f"📋 Question: '{state.question}'")
        self.logger.info(f"   Force using template: {prompt_key}")
        self.logger.info(f"   Detection result - is_time_query: {is_time_query}, has_time_info: {has_time_info}")
        
        # Get prompt template
        prompt_template = self.qa_prompts.get(prompt_key, {}).get(language)
        
        if not prompt_template:
            # Fallback to built-in prompt
            self.logger.warning(f"QA prompt template not found {prompt_key}:{language}, using built-in template")
            return self._build_fallback_prompt(state, context_memories, is_chinese)
        
        # Format prompt
        try:
            # Safely handle context_memories
            safe_context_memories = []
            for memory in context_memories:
                if memory is not None:
                    safe_context_memories.append(str(memory))
            
            context_str = "\n".join(safe_context_memories) if safe_context_memories else ("No relevant memories available" if language == "en" else "No relevant memories")
            
            # Get question date (from context)
            question_date = state.context.get("question_date", "") if state.context else ""
            
            # Check template parameters (support 2-param and 3-param templates)
            # 2-param: {question}, {context_memories}
            # 3-param: {}, {}, {} (LongMemEval style: memories, date, question)
            import inspect
            
            # Try formatting (smart parameter count detection)
            if "{}" in prompt_template:
                # Positional parameter format (LongMemEval style)
                prompt = prompt_template.format(
                    context_str,
                    question_date if question_date else "Unknown",
                    str(state.question)
                )
                if question_date:
                    self.logger.info(f"✅ Using question date: {question_date}")
                else:
                    self.logger.warning(f"⚠️ Question date not found, using default value")
            else:
                # Named parameter format (TiMem style)
                prompt = prompt_template.format(
                    question=str(state.question),
                    context_memories=context_str
                )
            
            self.logger.info(f"Using QA prompt template: {prompt_key}:{language}")
            return prompt
        except Exception as e:
            self.logger.error(f"Failed to format prompt: {e}")
            self.logger.error(f"Template content preview: {prompt_template[:200]}...")
            self.logger.error(f"Question: {state.question}")
            self.logger.error(f"Memory count: {len(context_memories)}")
            # Log more detailed debug info
            if context_memories:
                self.logger.error(f"First memory preview: {str(context_memories[0])[:100]}...")
            return self._build_fallback_prompt(state, context_memories, is_chinese)
    
    def _build_fallback_prompt(self, state: RetrievalState, context_memories: List[str], is_chinese: bool) -> str:
        """Build fallback prompt (original version)"""
        try:
            # Use global language config, if not set use passed is_chinese parameter
            use_chinese = self.global_language == "zh" if self.global_language in ["zh", "en"] else is_chinese
            
            # Safely handle memory content
            safe_memories = []
            for memory in context_memories:
                if memory is not None:
                    safe_memories.append(str(memory))
            
            memories_text = "\n".join(safe_memories) if safe_memories else ("No relevant memories available" if not use_chinese else "No relevant memories")
            question_text = str(state.question) if state.question else ("Unknown question" if not use_chinese else "Unknown question")
            
            if use_chinese:
                # Chinese fallback prompt
                prompt = """Based on the following memory information, answer the user's question. Please provide an accurate and concise answer.

Question: {question}

Relevant Memories:
{memories}

Please answer the question based on the memory content, with requirements:
1. Answer must be based on memory content, do not make up information
2. Keep it concise and clear, highlight key points
3. If memory information is insufficient for complete answer, please indicate
4. Use natural and fluent language

Answer:""".format(question=question_text, memories=memories_text)
            else:
                # English fallback prompt
                prompt = """Based on the following memory information, answer the user's question. Please provide an accurate and concise answer.

Question: {question}

Relevant Memories:
{memories}

Please answer the question based on the memory content, with requirements:
1. Base your answer on the memory content, do not make up information
2. Keep it concise and clear, highlighting key points
3. If the memory information is insufficient for a complete answer, please indicate so
4. Use natural and fluent language

Answer:""".format(question=question_text, memories=memories_text)
            
            return prompt
            
        except Exception as e:
            self.logger.error(f"Failed to build fallback prompt: {e}")
            # Simplest fallback option
            question_text = str(state.question) if state.question else "Unknown question"
            return f"Please answer this question: {question_text}"
    
    async def _generate_answer_with_llm(self, prompt: str) -> str:
        """Use LLM to generate answer"""
        try:
            llm_manager = await self._get_llm_manager()
            
            # Format message
            messages = llm_manager.format_chat_prompt("", prompt)
            
            # 📊 Log actual model config used (for debugging)
            self.logger.info(f"🤖 QA LLM call: model={self.qa_model}, temp={self.qa_temperature}, max_tokens={self.qa_max_tokens}")
            
            # 🔧 Call LLM with configured model parameters
            response = await llm_manager.chat(
                messages,
                model=self.qa_model,
                temperature=self.qa_temperature,
                max_tokens=self.qa_max_tokens
            )
            
            answer = response.content if response.content else "Sorry, unable to generate answer."
            
            # Clean and format answer
            answer = self._clean_answer(answer)
            
            return answer
            
        except Exception as e:
            self.logger.error(f"LLM answer generation failed: {str(e)}")
            return "Sorry, a technical issue occurred during answer generation."
    
    def _clean_answer(self, answer: str) -> str:
        """Clean and format answer"""
        # Remove extra whitespace
        answer = answer.strip()
        
        # Remove possible prompt residue
        if answer.startswith("Answer:") or answer.startswith("Answer:"):
            answer = answer.split("：", 1)[-1].split(":", 1)[-1].strip()
        
        # Ensure answer is not empty
        if not answer:
            answer = "Sorry, unable to generate answer based on available information."
        
        return answer
    
    def _calculate_answer_confidence(self, state: RetrievalState, answer: str) -> float:
        """Calculate answer confidence"""
        if not state.ranked_results or not answer:
            return 0.0
        
        # Base confidence: based on top memory scores
        top_scores = [result.get("fused_score", 0.0) for result in state.ranked_results[:3]]
        if top_scores:
            avg_top_score = sum(top_scores) / len(top_scores)
        else:
            avg_top_score = 0.0
        
        # Result count factor
        result_count = len(state.ranked_results)
        result_count_factor = min(1.0, result_count / 5)  # 5 results reach full score
        
        # Answer length factor
        answer_length = len(answer)
        if answer_length < 10:
            length_factor = 0.5  # Too short answer has lower confidence
        elif answer_length > 500:
            length_factor = 0.9  # Too long answer may contain redundant info
        else:
            length_factor = 1.0
        
        # Memory diversity factor
        levels = set(result.get("level", "") for result in state.ranked_results[:5])
        diversity_factor = min(1.0, len(levels) / 3)  # 3 different levels reach full score
        
        # Retrieval strategy factor
        strategy_count = len(state.selected_strategies)
        strategy_factor = min(1.0, strategy_count / 2)  # 2 strategies reach full score
        
        # Calculate composite confidence
        confidence = (
            avg_top_score * 0.4 +          # 40% based on memory quality
            result_count_factor * 0.2 +    # 20% based on result count
            length_factor * 0.1 +          # 10% based on answer length
            diversity_factor * 0.15 +      # 15% based on memory diversity
            strategy_factor * 0.15         # 15% based on strategy diversity
        )
        
        # Ensure confidence is in reasonable range
        confidence = max(self.min_confidence_threshold, min(1.0, confidence))
        
        return confidence
    
    def _extract_evidence(self, state: RetrievalState) -> List[str]:
        """Extract evidence supporting the answer"""
        evidence = []
        
        # Use top 3 most relevant memories as evidence
        for result in state.ranked_results[:3]:
            memory_id = result.get("id", "")
            if memory_id:
                evidence.append(memory_id)
        
        return evidence
    
    def _dict_to_state(self, state_dict: Dict[str, Any]) -> RetrievalState:
        """Convert dictionary to RetrievalState object"""
        state = RetrievalState()
        
        # Copy existing fields
        for key, value in state_dict.items():
            if hasattr(state, key):
                setattr(state, key, value)
                
        return state
    
    def _state_to_dict(self, state: RetrievalState) -> Dict[str, Any]:
        """Convert RetrievalState object to dictionary"""
        state_dict = {}
        
        # Copy all fields
        for key, value in state.__dict__.items():
            state_dict[key] = value
                
        return state_dict