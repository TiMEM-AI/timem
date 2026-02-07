"""
LLM-based Memory Refiner

Responsible for using large language models to refine recalled memories based on relevance,
filtering out noise memories unrelated to user questions.
Core principle: use relevance as the only judgment criterion, no hard limits on quantity and hierarchy.
"""

import asyncio
import json
import re
from typing import Dict, Any, Optional, List, Tuple

from llm.llm_manager import get_llm
from llm.base_llm import MessageRole, ModelConfig
from llm.zhipuai_adapter import ZhipuAIAdapter
from llm.openai_adapter import OpenAIAdapter

from timem.utils.prompt_manager import get_prompt_manager
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_llm_config
from timem.utils.retrieval_config_manager import get_retrieval_config_manager
from timem.workflows.retrieval_state import RetrievalStateValidator

logger = get_logger(__name__)


class MemoryRefiner:
    """LLM-based memory refiner"""

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        state_validator: Optional[RetrievalStateValidator] = None,
        debug_mode: bool = False,
    ):
        """
        Initialize memory refiner

        Args:
            llm_provider: LLM provider, if None use settings from config file
            state_validator: State validator
            debug_mode: Whether to enable debug mode
        """
        self.debug_mode = debug_mode
        self.state_validator = state_validator or RetrievalStateValidator()
        self.prompt_manager = get_prompt_manager()
        self.logger = get_logger(__name__)

        # Get LLM config
        self.llm_config = get_llm_config()

        # Get memory refiner config
        self.retrieval_config_manager = get_retrieval_config_manager()
        self.refiner_config = self.retrieval_config_manager.get_config().get("memory_refiner", {})

        # Initialize LLM instance
        self.llm = self._init_llm(llm_provider)

        # Validate prompt templates
        self._validate_prompt_templates()

        self.logger.info("MemoryRefiner initialization complete")

    def _init_llm(self, llm_provider: Optional[str] = None):
        """Initialize LLM instance using memory refiner specific config."""
        try:
            if not self.refiner_config:
                self.logger.warning("Memory refiner configuration not found, using default LLM configuration")
                return get_llm(llm_provider)

            provider = llm_provider or self.refiner_config.get("llm_provider", "openai")
            model = self.refiner_config.get("llm_model", "gpt-4o-mini")
            temperature = self.refiner_config.get("temperature", 0.3)
            max_tokens = self.refiner_config.get("max_tokens", 1024)

            self.logger.info(f"Memory refiner LLM configuration: provider={provider}, model={model}")

            model_config = ModelConfig(model_name=model, temperature=temperature, max_tokens=max_tokens)

            if provider == "zhipuai":
                if self.debug_mode:
                    self.logger.info(f"Creating Zhipu AI adapter: {model}, temperature={temperature}")
                return ZhipuAIAdapter(model_config)

            if provider == "openai":
                if self.debug_mode:
                    self.logger.info(f"Creating OpenAI adapter: {model}, temperature={temperature}")
                return OpenAIAdapter(model_config)

            self.logger.warning(f"Unknown LLM provider: {provider}, using default configuration")
            return get_llm(llm_provider)

        except Exception as e:
            self.logger.error(f"Failed to initialize LLM: {e}")
            return get_llm(llm_provider)

    def _validate_prompt_templates(self):
        """Validate that required prompt templates exist."""
        template_name = "memory_refiner"
        try:
            prompt_template = self.prompt_manager.get_prompt(template_name)
            if not prompt_template:
                self.logger.warning(f"Missing prompt template: {template_name}")
            else:
                self.logger.info(f"Prompt template {template_name} validation successful")
        except Exception as e:
            self.logger.warning(f"Error validating prompt template {template_name}: {e}")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph node standard interface - Execute memory refining."""
        try:
            self.logger.info("Starting memory refining")

            question = state.get("question", "")
            memories = state.get("ranked_results", [])
            query_complexity = state.get("query_complexity", 0)

            if not question:
                self.logger.warning("Question is empty, skipping memory refining")
                state["memory_refiner_enabled"] = False
                return state

            if not memories:
                self.logger.warning("No memories to analyze, skipping memory refining")
                state["memory_refiner_enabled"] = False
                state["memories_before_memory_refiner"] = []
                state["memories_after_memory_refiner"] = []
                return state

            original_count = len(memories)
            self.logger.info(f"Starting to refine {original_count} memories")

            max_retries = self.refiner_config.get("retry", {}).get("max_retries", 3)
            relevant_ids, analysis_metadata = await self.analyze_memory_relevance(
                question=question,
                memories=memories,
                query_complexity=query_complexity,
                max_retries=max_retries,
            )

            if relevant_ids is None:
                self.logger.warning("Memory refining failed, falling back to no refining")
                state["memory_refined"] = False
                state["memory_refiner_enabled"] = True
                state["memory_refiner_failed"] = True
                state["original_memory_count"] = original_count
                state["refined_memory_count"] = original_count
                state["refinement_retention_rate"] = 1.0
                state["memories_before_memory_refiner"] = memories
                state["memories_after_memory_refiner"] = memories
                return state

            filtered_memories = self._filter_memories_by_ids(memories, relevant_ids)
            refined_count = len(filtered_memories)
            retention_rate = refined_count / original_count if original_count > 0 else 0.0

            # Empty result protection
            protection_config = self.refiner_config.get("empty_result_protection", {})
            protection_enabled = protection_config.get("enabled", True)
            fallback_count_config = protection_config.get("fallback_count", 5)
            min_original_count = protection_config.get("min_original_count", 3)

            if refined_count == 0 and original_count >= min_original_count and protection_enabled:
                self.logger.warning("Memory refiner returned empty result, enabling protection mechanism")
                fallback_count = min(fallback_count_config, original_count)
                filtered_memories = memories[:fallback_count]
                refined_count = len(filtered_memories)
                retention_rate = refined_count / original_count

                analysis_metadata["fallback_used"] = True
                analysis_metadata["fallback_count"] = fallback_count
                analysis_metadata["fallback_reason"] = "Memory refiner returned empty result"
                analysis_metadata["protection_enabled"] = True
            elif refined_count == 0 and 0 < original_count < min_original_count:
                self.logger.warning(
                    f"Original memory count is small ({original_count}), preserving all memories to avoid over-refining"
                )
                filtered_memories = memories
                refined_count = original_count
                retention_rate = 1.0

                analysis_metadata["fallback_used"] = True
                analysis_metadata["fallback_count"] = original_count
                analysis_metadata["fallback_reason"] = f"Original memory count is small ({original_count})"
                analysis_metadata["protection_enabled"] = True
            else:
                analysis_metadata["fallback_used"] = False
                analysis_metadata["protection_enabled"] = protection_enabled

            state["ranked_results"] = filtered_memories
            state["memory_refined"] = True
            state["memory_refiner_enabled"] = True
            state["memory_refiner_failed"] = False
            state["original_memory_count"] = original_count
            state["refined_memory_count"] = refined_count
            state["refinement_retention_rate"] = retention_rate
            state["memory_refiner_metadata"] = analysis_metadata
            state["memories_before_memory_refiner"] = memories
            state["memories_after_memory_refiner"] = filtered_memories

            self.logger.info(
                f"Memory refining complete: {original_count} → {refined_count} memories (retention rate: {retention_rate:.1%})"
            )

            return state

        except Exception as e:
            error_msg = f"Memory refining failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            state["memory_refiner_enabled"] = True
            state["memory_refiner_failed"] = True
            memories = state.get("ranked_results", [])
            state["memories_before_memory_refiner"] = memories
            state["memories_after_memory_refiner"] = memories
            return state

    async def analyze_memory_relevance(
        self,
        question: str,
        memories: List[Dict[str, Any]],
        query_complexity: int,
        max_retries: int = 3,
    ) -> Tuple[Optional[List[int]], Dict[str, Any]]:
        """Analyze memory relevance and return list of relevant memory IDs."""
        numbered_memories, reordered_indices = self._assign_memory_numbers(memories)

        result = await self._call_llm_with_retry(
            question=question,
            numbered_memories=numbered_memories,
            query_complexity=query_complexity,
            max_retries=max_retries,
        )

        if result is None:
            return None, {"retry_count": max_retries, "success": False, "error": "All retries failed"}

        retry_count = result.get("_retry_count", 0)
        reasoning = result.get("reasoning", "")
        relevant_ids = result.get("relevant_ids", [])

        valid_reordered_ids = [i for i in relevant_ids if 1 <= i <= len(memories)]
        valid_ids = [reordered_indices[i - 1] + 1 for i in valid_reordered_ids]

        metadata = {
            "retry_count": retry_count,
            "success": True,
            "reasoning": reasoning,
            "mode": "keep",
            "original_ids": relevant_ids,
            "valid_ids": valid_ids,
            "invalid_ids": [i for i in relevant_ids if i not in valid_reordered_ids],
            "kept_count": len(valid_ids),
            "total_memories": len(memories),
        }

        return valid_ids, metadata

    async def _call_llm_with_retry(
        self,
        question: str,
        numbered_memories: Dict[int, Dict[str, Any]],
        query_complexity: int,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        retry_count = 0
        last_error = None

        retry_config = self.refiner_config.get("retry", {})
        fallback_on_error = retry_config.get("fallback_on_error", True)

        while retry_count <= max_retries:
            try:
                prompt_messages = self._build_prompt(
                    question=question,
                    numbered_memories=numbered_memories,
                    query_complexity=query_complexity,
                )

                if self.debug_mode:
                    self.logger.info(f"Calling LLM (retry {retry_count}/{max_retries})")

                llm_messages = [self.llm.create_message(MessageRole.USER, m["content"]) for m in prompt_messages]
                response = await self.llm.chat(llm_messages)

                result = self._parse_json_response(response.content)

                is_valid, validation_msg = self._validate_result(result, len(numbered_memories), query_complexity)
                if is_valid:
                    result["_retry_count"] = retry_count
                    return result

                if validation_msg == "empty_result":
                    retry_on_empty = retry_config.get("retry_on_empty", False)
                    if not retry_on_empty:
                        self.logger.info("LLM determined all memories are unrelated, no retry")
                        result["_retry_count"] = retry_count
                        return result

                retry_count += 1
                self.logger.warning(f"Result validation failed: {validation_msg}, retry {retry_count}/{max_retries}")

            except json.JSONDecodeError as e:
                last_error = f"JSON parsing failed: {e}"
                retry_count += 1
                self.logger.warning(f"{last_error}, retry {retry_count}/{max_retries}")

            except Exception as e:
                last_error = f"LLM call failed: {e}"
                retry_count += 1
                self.logger.error(f"{last_error}, retry {retry_count}/{max_retries}")

            if retry_count <= max_retries:
                await asyncio.sleep(0.5)

        if fallback_on_error:
            self.logger.error(f"Memory refining failed ({max_retries} retries), falling back to no refining")
            return None

        raise RuntimeError(f"Memory refining failed: {last_error}")

    def _assign_memory_numbers(self, memories: List[Dict[str, Any]]) -> Tuple[Dict[int, Dict[str, Any]], List[int]]:
        level_priority = {"L1": 0, "L2": 1, "L3": 2, "L4": 3, "L5": 4}
        indexed_memories = [(idx, mem) for idx, mem in enumerate(memories)]
        sorted_memories = sorted(indexed_memories, key=lambda x: (level_priority.get(x[1].get("level", "L1"), 99), x[0]))

        numbered_memories: Dict[int, Dict[str, Any]] = {}
        reordered_indices: List[int] = []

        for new_idx, (original_idx, memory) in enumerate(sorted_memories, start=1):
            numbered_memories[new_idx] = memory
            reordered_indices.append(original_idx)

        return numbered_memories, reordered_indices

    def _get_prompt_template_by_complexity(self, complexity: int) -> str:
        strategy_aware = self.refiner_config.get("strategy_aware", False)
        if not strategy_aware:
            return "memory_refiner"

        prompt_templates = self.refiner_config.get("prompt_templates", {})
        template_name = prompt_templates.get(f"complexity_{complexity}")
        if not template_name:
            self.logger.warning(f"No template configuration found for complexity {complexity}, using default template")
            return "memory_refiner"

        prompt_template = self.prompt_manager.get_prompt(template_name)
        if not prompt_template:
            self.logger.warning(f"Template {template_name} does not exist, falling back to default template")
            return "memory_refiner"

        self.logger.info(f"Using template for complexity {complexity}: {template_name}")
        return template_name

    def _build_prompt(
        self,
        question: str,
        numbered_memories: Dict[int, Dict[str, Any]],
        query_complexity: int,
    ) -> List[Dict[str, str]]:
        template_name = self._get_prompt_template_by_complexity(query_complexity)
        numbered_memories_text = self._build_numbered_memories_text(numbered_memories)

        complexity_desc_map = {0: "Simple query (fact query)", 1: "Mixed query (association analysis)", 2: "Complex query (deep reasoning)"}
        complexity_desc = complexity_desc_map.get(query_complexity, "Unknown")

        try:
            prompt_template = self.prompt_manager.get_prompt(template_name)
            if not prompt_template:
                raise ValueError(f"Prompt template {template_name} does not exist")

            formatted_prompt = prompt_template.format(
                question=question,
                complexity_desc=complexity_desc,
                total_count=len(numbered_memories),
                numbered_memories=numbered_memories_text,
            )

        except Exception as e:
            self.logger.error(f"Failed to build prompt: {e}, using default prompt")
            formatted_prompt = f"""You are a memory refiner. Refine and return a list of relevant memory IDs (JSON format).

Question: {question}

Memory list:
{numbered_memories_text}

Output format: {{\"relevant_ids\": [array of IDs]}}"""

        return [{"role": "user", "content": formatted_prompt}]

    def _build_numbered_memories_text(self, numbered_memories: Dict[int, Dict[str, Any]]) -> str:
        prompt_config = self.refiner_config.get("prompt_config", {})
        show_metadata = prompt_config.get("show_memory_metadata", True)

        lines: List[str] = []
        for num, memory in numbered_memories.items():
            level = memory.get("level", "L1")
            title = memory.get("title", "No title")
            content = memory.get("content", "")

            lines.append(f"[{num}-{level}] {title}")
            lines.append(f"  Content: {content}")

            if show_metadata:
                created_at = memory.get("created_at", "")
                session_id = memory.get("session_id", "")
                if created_at:
                    lines.append(f"  Time: {created_at}")
                if session_id:
                    lines.append(f"  Session: {session_id}")

            lines.append("")

        return "\n".join(lines)

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        response = response.strip()

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        json_match = re.search(r"\{.*?\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError(f"Unable to extract JSON from response: {response[:200]}", response, 0)

    def _validate_result(self, result: Dict[str, Any], total_memories: int, query_complexity: int = 0) -> Tuple[bool, str]:
        if not result or not isinstance(result, dict):
            return False, "empty_result"

        if "relevant_ids" not in result:
            return False, "missing_field"

        ids_to_check = result.get("relevant_ids", [])
        if not isinstance(ids_to_check, list):
            return False, "invalid_format"

        valid_ids = [i for i in ids_to_check if isinstance(i, int) and 1 <= i <= total_memories]
        if not valid_ids and ids_to_check:
            return False, "invalid_ids"

        return True, "valid"

    def _filter_memories_by_ids(self, memories: List[Dict[str, Any]], relevant_ids: List[int]) -> List[Dict[str, Any]]:
        if not relevant_ids:
            self.logger.warning("LLM determined all memories are unrelated, returning empty list")
            return []

        filtered_memories: List[Dict[str, Any]] = []
        for i in relevant_ids:
            if 1 <= i <= len(memories):
                filtered_memories.append(memories[i - 1])

        return filtered_memories
