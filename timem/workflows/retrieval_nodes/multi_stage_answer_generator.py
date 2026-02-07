"""
Multi-Stage Chain-of-Thought (COT) Answer Generator

Implements three-stage answer generation process:
1. Evidence Collection
2. Deep Reasoning
3. Answer Synthesis

Goal: Improve evaluation scores while maintaining reasoning quality by separating internal reasoning from external output
"""

import time
import json
from typing import Dict, List, Any, Optional
from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator
from timem.workflows.nodes.memory_time_sorter import MemoryTimeSorter
from timem.workflows.retrieval_nodes.answer_generator import AnswerGenerator
from timem.utils.json_parser import get_json_parser
from llm.llm_manager import get_llm
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_config

logger = get_logger(__name__)


class MultiStageAnswerGenerator:
    """Multi-stage chain-of-thought answer generator"""
    
    def __init__(self, 
                 llm_manager: Optional[Any] = None,
                 state_validator: Optional[RetrievalStateValidator] = None,
                 time_sorter: Optional[MemoryTimeSorter] = None,
                 fallback_generator: Optional[AnswerGenerator] = None):
        """
        Initialize multi-stage answer generator
        
        Args:
            llm_manager: LLM manager
            state_validator: State validator
            time_sorter: Time sorter
            fallback_generator: Single-stage answer generator (for fallback)
        """
        self.llm_manager = llm_manager
        self.state_validator = state_validator or RetrievalStateValidator()
        self.time_sorter = time_sorter or MemoryTimeSorter()
        self.fallback_generator = fallback_generator
        self.json_parser = get_json_parser()
        self.logger = get_logger(__name__)
        
        # Load configuration
        self.qa_prompts = get_config("multi_stage_qa_prompts")
        self.retrieval_config = get_config("retrieval_config") or {}
        
        # Debug: Check configuration loading
        if not self.qa_prompts:
            self.logger.error("❌ Multi-stage COT prompt configuration loading failed")
            raise ValueError("Multi-stage COT prompt configuration not found, please check config/multi_stage_qa_prompts.yaml file")
        else:
            self.logger.info(f"✅ Multi-stage COT prompt configuration loaded successfully, supported languages: {list(self.qa_prompts.get('stage1_evidence_collection', {}).keys())}")
        
        # Get multi-stage COT configuration
        self.cot_config = self.retrieval_config.get("answer_generation", {}).get("multi_stage_cot", {})
        self.max_retry = self.cot_config.get("max_retry_on_parse_error", 3)
        self.fallback_to_single_stage = self.cot_config.get("fallback_to_single_stage", True)
        
        # Get global language configuration
        self.global_language = self._get_global_language()
        self.logger.info(f"Multi-stage COT answer generator initialization complete, language: {self.global_language}")
    
    def _get_global_language(self) -> str:
        """Get global language configuration"""
        try:
            app_config = get_config("app")
            language = app_config.get("language", "en")
            return language.lower()
        except Exception as e:
            self.logger.warning(f"Failed to get global language configuration: {e}, using default 'en'")
            return "en"
    
    async def _get_llm_manager(self):
        """Get LLM manager instance"""
        if self.llm_manager is None:
            self.llm_manager = get_llm()
        return self.llm_manager
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run three-stage COT answer generation
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            # Check if multi-stage COT is enabled
            state_use_cot = retrieval_state.use_multi_stage_cot
            dict_use_cot = state.get("use_multi_stage_cot", False)
            
            self.logger.info(f"🔍 Multi-stage COT enable check:")
            self.logger.info(f"  - retrieval_state.use_multi_stage_cot: {state_use_cot}")
            self.logger.info(f"  - state['use_multi_stage_cot']: {dict_use_cot}")
            
            if not state_use_cot and not dict_use_cot:
                self.logger.warning("❌ Multi-stage COT not enabled, using standard answer generation (fallback)")
                # If fallback generator exists, use it; otherwise return error
                if self.fallback_generator:
                    return await self.fallback_generator.run(state)
                else:
                    retrieval_state.errors.append("Multi-stage COT not enabled and no fallback generator")
                    return self._state_to_dict(retrieval_state)
            
            # Check if there are retrieval results
            if not retrieval_state.ranked_results:
                self.logger.warning("No retrieval results, unable to generate answer")
                retrieval_state.answer = "Sorry, I could not find relevant memory information to answer your question."
                retrieval_state.confidence = 0.0
                retrieval_state.evidence = []
                return self._state_to_dict(retrieval_state)
            
            self.logger.info("🔄 ============ Starting three-stage COT answer generation ============")
            
            # Build context memories (using original AnswerGenerator method)
            context_memories = self._build_context(retrieval_state)
            
            try:
                # Stage 1: Evidence Collection
                stage1_start = time.time()
                evidence_result, stage1_tokens = await self._stage1_evidence_collection(
                    retrieval_state.question,
                    context_memories
                )
                retrieval_state.cot_evidence = evidence_result
                retrieval_state.cot_stage_times['stage1'] = time.time() - stage1_start
                retrieval_state.cot_stage_tokens['stage1'] = stage1_tokens
                self.logger.info(f"✅ Stage 1 complete (Evidence Collection): {retrieval_state.cot_stage_times['stage1']:.2f}s, tokens: {stage1_tokens}")
                self.logger.info(f"   Evidence count: {len(evidence_result.get('key_facts', []))}")
                
                # Stage 2: Deep Reasoning
                stage2_start = time.time()
                reasoning_result, stage2_tokens = await self._stage2_deep_reasoning(
                    retrieval_state.question,
                    evidence_result
                )
                retrieval_state.cot_reasoning = reasoning_result
                retrieval_state.cot_stage_times['stage2'] = time.time() - stage2_start
                retrieval_state.cot_stage_tokens['stage2'] = stage2_tokens
                self.logger.info(f"✅ Stage 2 complete (Deep Reasoning): {retrieval_state.cot_stage_times['stage2']:.2f}s, tokens: {stage2_tokens}")
                self.logger.info(f"   Preliminary answer: {reasoning_result.get('preliminary_answer', '')[:100]}...")
                
                # Stage 3: Answer Synthesis (based only on reasoning result, no evidence to reduce redundancy)
                stage3_start = time.time()
                final_result, stage3_tokens = await self._stage3_answer_synthesis(
                    retrieval_state.question,
                    reasoning_result  # Only pass reasoning result, not evidence
                )
                retrieval_state.cot_final_answer = final_result.get('concise_answer', '')
                retrieval_state.cot_stage_times['stage3'] = time.time() - stage3_start
                retrieval_state.cot_stage_tokens['stage3'] = stage3_tokens
                
                # Calculate total token usage and optimization effect
                total_tokens = stage1_tokens + stage2_tokens + stage3_tokens
                retrieval_state.cot_stage_tokens['total'] = total_tokens
                self.logger.info(f"✅ Stage 3 complete (Answer Synthesis): {retrieval_state.cot_stage_times['stage3']:.2f}s, tokens: {stage3_tokens}")
                self.logger.info(f"   Final concise answer: {final_result.get('concise_answer', '')}")
                self.logger.info(f"📊 Total token usage: {total_tokens} (Stage 1: {stage1_tokens}, Stage 2: {stage2_tokens}, Stage 3: {stage3_tokens})")
                
                # Set final answer and confidence
                retrieval_state.answer = final_result.get('concise_answer', '')
                retrieval_state.confidence = final_result.get('confidence', reasoning_result.get('confidence_level', 0.5))
                
                # Build complete reasoning chain (for debugging)
                retrieval_state.cot_full_reasoning = self._build_full_reasoning_text(
                    evidence_result,
                    reasoning_result,
                    final_result
                )
                
                # Extract evidence
                retrieval_state.evidence = self._extract_evidence_from_cot(
                    evidence_result,
                    retrieval_state
                )
                
                # Save formatted memories
                retrieval_state.formatted_context_memories = context_memories
                
                self.logger.info("✅ ============ Three-stage COT answer generation complete ============")
                self.logger.info(f"Final answer: {retrieval_state.answer}")
                self.logger.info(f"Answer length: {len(retrieval_state.answer)} characters")
                self.logger.info(f"Confidence: {retrieval_state.confidence:.3f}")
                
            except Exception as e:
                import traceback
                error_msg = f"Three-stage COT execution failed: {str(e)}"
                self.logger.error(error_msg)
                self.logger.error(f"Full error traceback: {traceback.format_exc()}")
                retrieval_state.errors.append(error_msg)
                
                # Try fallback to single-stage generation
                if self.fallback_to_single_stage and self.fallback_generator:
                    self.logger.warning("⚠️ Falling back to single-stage answer generation")
                    retrieval_state.warnings.append("Multi-stage COT failed, fallen back to single-stage generation")
                    return await self.fallback_generator.run(state)
                else:
                    retrieval_state.answer = "Sorry, an error occurred during answer generation."
                    retrieval_state.confidence = 0.0
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            error_msg = f"Multi-stage COT answer generator execution failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            state["answer"] = "Sorry, a serious error occurred during answer generation."
            state["confidence"] = 0.0
            return state
    
    async def _stage1_evidence_collection(self, question: str, context_memories: List[str]) -> tuple[Dict[str, Any], int]:
        """
        Stage 1: Evidence Collection
        
        Systematically extract all relevant evidence from memories
        
        Returns:
            tuple: (Evidence result dictionary, token usage)
        """
        self.logger.info("📋 Stage 1: Evidence Collection")
        
        # Get prompt template
        prompt_template = self.qa_prompts.get("stage1_evidence_collection", {}).get(self.global_language)
        if not prompt_template:
            raise ValueError(f"Stage 1 prompt template not found: {self.global_language}")
        
        # Format prompt
        context_str = "\n".join(context_memories) if context_memories else "No relevant memories available"
        prompt = prompt_template.format(
            question=question,
            context_memories=context_str
        )
        
        # Call LLM
        llm_manager = await self._get_llm_manager()
        messages = llm_manager.format_chat_prompt("", prompt)
        
        for retry in range(self.max_retry):
            try:
                response = await llm_manager.chat(messages)
                response_text = response.content if response.content else ""
                
                # Get token usage
                tokens_used = getattr(response, 'total_tokens', 0) or 0
                
                # Parse JSON response (simplified format: only key_facts)
                expected_keys = ["key_facts"]
                result = self.json_parser.parse_llm_json_response(response_text, expected_keys)
                
                self.logger.info(f"✅ Evidence collection successful: {len(result.get('key_facts', []))} key facts")
                return result, tokens_used
                
            except Exception as e:
                self.logger.warning(f"Stage 1 JSON parsing failed (retry {retry + 1}/{self.max_retry}): {e}")
                if retry == self.max_retry - 1:
                    # Last retry failed, return simplified result
                    self.logger.error("Stage 1 all retries failed, returning simplified evidence result")
                    return {
                        "key_facts": [mem[:200] for mem in context_memories[:3]],
                        "evidence_sufficiency": "partial"
                    }, 0  # Token is 0 on failure
    
    async def _stage2_deep_reasoning(self, question: str, evidence_result: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
        """
        Stage 2: Deep Reasoning
        
        Perform logical reasoning based on evidence
        
        Returns:
            tuple: (Reasoning result dictionary, token usage)
        """
        self.logger.info("🔍 Stage 2: Deep Reasoning")
        
        # Get prompt template
        prompt_template = self.qa_prompts.get("stage2_deep_reasoning", {}).get(self.global_language)
        if not prompt_template:
            raise ValueError(f"Stage 2 prompt template not found: {self.global_language}")
        
        # Format prompt
        evidence_json = json.dumps(evidence_result, ensure_ascii=False, indent=2)
        prompt = prompt_template.format(
            question=question,
            evidence_json=evidence_json
        )
        
        # Call LLM
        llm_manager = await self._get_llm_manager()
        messages = llm_manager.format_chat_prompt("", prompt)
        
        for retry in range(self.max_retry):
            try:
                response = await llm_manager.chat(messages)
                response_text = response.content if response.content else ""
                
                # Get token usage
                tokens_used = getattr(response, 'total_tokens', 0) or 0
                
                # Parse JSON response (simplified format: reasoning_chain and preliminary_answer)
                expected_keys = ["reasoning_chain", "preliminary_answer"]
                result = self.json_parser.parse_llm_json_response(response_text, expected_keys)
                
                self.logger.info(f"✅ Reasoning complete, preliminary answer: {result.get('preliminary_answer', '')[:50]}...")
                return result, tokens_used
                
            except Exception as e:
                self.logger.warning(f"Stage 2 JSON parsing failed (retry {retry + 1}/{self.max_retry}): {e}")
                if retry == self.max_retry - 1:
                    # Last retry failed, return simplified result
                    self.logger.error("Stage 2 all retries failed, returning simplified reasoning result")
                    # Try to extract key facts from evidence as answer
                    key_facts = evidence_result.get("key_facts", [])
                    fallback_answer = key_facts[0] if key_facts else "Unable to generate answer"
                    return {
                        "reasoning_chain": f"Based on evidence: {fallback_answer[:100]}",
                        "confidence_level": 0.3,
                        "preliminary_answer": fallback_answer
                    }, 0  # Token is 0 on failure
    
    async def _stage3_answer_synthesis(self, question: str, 
                                      reasoning_result: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
        """
        Stage 3: Answer Synthesis
        
        Extract concise final answer based only on reasoning result (progressive context filtering optimization)
        No longer pass evidence result to reduce redundancy and noise
        
        Returns:
            tuple: (Final answer dictionary, token usage)
        """
        self.logger.info("✨ Stage 3: Answer Synthesis (Progressive Filtering)")
        
        # Get prompt template
        prompt_template = self.qa_prompts.get("stage3_answer_synthesis", {}).get(self.global_language)
        if not prompt_template:
            raise ValueError(f"Stage 3 prompt template not found: {self.global_language}")
        
        # Format prompt (only use reasoning result, don't pass evidence)
        reasoning_json = json.dumps(reasoning_result, ensure_ascii=False, indent=2)
        prompt = prompt_template.format(
            question=question,
            reasoning_json=reasoning_json
        )
        
        # Call LLM
        llm_manager = await self._get_llm_manager()
        messages = llm_manager.format_chat_prompt("", prompt)
        
        for retry in range(self.max_retry):
            try:
                response = await llm_manager.chat(messages)
                response_text = response.content if response.content else ""
                
                # Get token usage
                tokens_used = getattr(response, 'total_tokens', 0) or 0
                
                # Parse JSON response (only need concise_answer field)
                expected_keys = ["concise_answer"]
                result = self.json_parser.parse_llm_json_response(response_text, expected_keys)
                
                concise_answer = result.get('concise_answer', '')
                word_count = len(concise_answer.split())
                self.logger.info(f"✅ Answer synthesis complete: {concise_answer}")
                self.logger.info(f"   Answer length: {word_count} words / {len(concise_answer)} characters")
                
                return result, tokens_used
                
            except Exception as e:
                self.logger.warning(f"Stage 3 JSON parsing failed (retry {retry + 1}/{self.max_retry}): {e}")
                if retry == self.max_retry - 1:
                    # Last retry failed, use preliminary answer
                    self.logger.error("Stage 3 all retries failed, using preliminary answer")
                    preliminary_answer = reasoning_result.get("preliminary_answer", "")
                    return {
                        "concise_answer": preliminary_answer[:50] if preliminary_answer else "Unable to generate answer"
                    }, 0  # Token is 0 on failure
    
    def _build_context(self, state: RetrievalState) -> List[str]:
        """Build context memories with time information (reuse original AnswerGenerator logic)"""
        # Directly reuse original AnswerGenerator logic
        # For simplicity, create a temporary AnswerGenerator instance
        from timem.workflows.retrieval_nodes.answer_generator import AnswerGenerator
        temp_generator = AnswerGenerator(
            llm_manager=self.llm_manager,
            state_validator=self.state_validator,
            time_sorter=self.time_sorter
        )
        return temp_generator._build_context(state)
    
    def _build_full_reasoning_text(self, evidence_result: Dict[str, Any], 
                                   reasoning_result: Dict[str, Any],
                                   final_result: Dict[str, Any]) -> str:
        """Build complete reasoning chain text (for debugging)"""
        parts = []
        
        # Evidence section (new format: key_facts)
        parts.append("[Evidence Collection]")
        key_facts = evidence_result.get("key_facts", [])
        if key_facts:
            parts.append("; ".join(key_facts[:3]))
        else:
            parts.append("No key facts")
        
        # Reasoning section (new format: reasoning_chain + preliminary_answer)
        parts.append("\n[Reasoning Process]")
        reasoning_chain = reasoning_result.get("reasoning_chain", "")
        if reasoning_chain:
            parts.append(f"  {reasoning_chain[:200]}")
        parts.append(f"\nPreliminary answer: {reasoning_result.get('preliminary_answer', '')}")
        
        # Final answer
        parts.append("\n[Final Answer]")
        parts.append(final_result.get("concise_answer", ""))
        
        return "\n".join(parts)
    
    def _extract_evidence_from_cot(self, evidence_result: Dict[str, Any], 
                                   state: RetrievalState) -> List[str]:
        """Extract evidence list from COT evidence (new format: only use key_facts)"""
        evidence_list = []
        
        # Extract from key_facts
        key_facts = evidence_result.get("key_facts", [])
        for fact in key_facts[:5]:  # Extract top 5 key facts
            if fact and isinstance(fact, str):
                evidence_list.append(fact[:200])  # Limit length
        
        # If not enough evidence, supplement from ranked_results
        if len(evidence_list) < 3 and state.ranked_results:
            for result in state.ranked_results[:3]:
                memory_id = result.get("id", "")
                if memory_id and str(memory_id) not in evidence_list:
                    evidence_list.append(str(memory_id)[:100])
        
        return evidence_list
    
    def _dict_to_state(self, state_dict: Dict[str, Any]) -> RetrievalState:
        """Convert dictionary to RetrievalState object"""
        state = RetrievalState()
        for key, value in state_dict.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state
    
    def _state_to_dict(self, state: RetrievalState) -> Dict[str, Any]:
        """Convert RetrievalState object to dictionary"""
        state_dict = {}
        for key, value in state.__dict__.items():
            state_dict[key] = value
        return state_dict

