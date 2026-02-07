"""
LLM-based retrieval planner.

This node uses a large language model to estimate the query complexity and (optionally)
extract keywords that can help downstream routing and retrieval.

Complexity levels:
- 0: Simple
- 1: Mixed
- 2: Complex
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, Tuple
from llm.llm_manager import get_llm
from llm.base_llm import MessageRole, ModelConfig
from llm.zhipuai_adapter import ZhipuAIAdapter
from llm.openai_adapter import OpenAIAdapter
from timem.utils.prompt_manager import get_prompt_manager
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_llm_config

logger = get_logger(__name__)


class LLMRetrievalPlanner:
    """LLM-based retrieval planner (complexity + keyword extraction)."""
    
    def __init__(self, llm_provider: Optional[str] = None, debug_mode: bool = False):
        """
        Initialize LLM retrieval planner
        
        Args:
            llm_provider: LLM provider; if None, use retrieval-planner-specific configuration
            debug_mode: Whether to enable debug mode, showing detailed prompt information
        """
        self.debug_mode = debug_mode
        self.prompt_manager = get_prompt_manager()
        self.logger = get_logger(__name__)
        
        # Get LLM configuration
        self.llm_config = get_llm_config()
        
        # Initialize LLM instance
        self.llm = self._init_llm(llm_provider)
        
        # Validate prompt template
        self._validate_prompt_template()
        
    def _init_llm(self, llm_provider: Optional[str] = None):
        """
        Initialize LLM instance using retrieval planner specific configuration
        
        Args:
            llm_provider: LLM provider, if None use settings from config file
            
        Returns:
            LLM instance
        """
        try:
            # Get retrieval-planner-specific configuration
            retrieval_planner_config = self.llm_config.get('retrieval_planner', {})
            
            if not retrieval_planner_config:
                self.logger.warning("Retrieval-planner-specific configuration not found; using default LLM configuration")
                return get_llm(llm_provider)
            
            # Use configured provider and model
            provider = llm_provider or retrieval_planner_config.get('provider', 'zhipuai')
            model = retrieval_planner_config.get('model', 'glm-4-flash')
            temperature = retrieval_planner_config.get('temperature', 0.7)
            max_tokens = retrieval_planner_config.get('max_tokens', 2048)
            
            self.logger.info(f"LLM retrieval planner configuration: provider={provider}, model={model}")
            
            if provider == 'zhipuai':
                # Create Zhipu AI specific configuration
                model_config = ModelConfig(
                    model_name=model,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                # Get API key
                zhipuai_config = self.llm_config.get('providers', {}).get('zhipuai', {})
                api_key = zhipuai_config.get('api_key')
                
                if not api_key:
                    raise ValueError("Zhipu AI API key configuration not found")
                
                # Create ZhipuAI adapter instance - fix parameter passing
                llm_instance = ZhipuAIAdapter(model_config)
                
                if self.debug_mode:
                    self.logger.info(f"Creating Zhipu AI adapter: {model}, temperature={temperature}, max_tokens={max_tokens}")
                
                return llm_instance
            elif provider == 'openai':
                # Create OpenAI specific configuration, support multiple API key concurrency
                model_config = ModelConfig(
                    model_name=model,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                # Create OpenAI adapter instance, pass correct model_config
                llm_instance = OpenAIAdapter(config=model_config)
                
                if self.debug_mode:
                    self.logger.info(f"Creating OpenAI adapter: {model}, temperature={temperature}, max_tokens={max_tokens}")
                    self.logger.info("OpenAI retrieval planner supports 20 API key concurrency")
                
                return llm_instance
            else:
                # For other providers, use default method
                return get_llm(provider)
                
        except Exception as e:
            self.logger.error(f"Failed to initialize LLM retrieval planner: {e}")
            self.logger.warning("Falling back to default LLM configuration")
            return get_llm(llm_provider)
    
    def get_model_info_sync(self) -> Dict[str, Any]:
        """
        Synchronously get model information
        
        Returns:
            Dict[str, Any]: Model information
        """
        try:
            if hasattr(self.llm, 'config') and hasattr(self.llm.config, 'model_name'):
                model_name = self.llm.config.model_name
                
                # Basic model information
                # Determine provider based on model name
                provider = "openai" if "gpt" in model_name.lower() else "zhipuai"
                
                model_info = {
                    "model_name": model_name,
                    "provider": provider,
                    "type": "chat",
                    "temperature": self.llm.config.temperature,
                    "max_tokens": self.llm.config.max_tokens,
                    "retrieval_planner_specific": True,  # Mark as retrieval planner specific
                    "independent_config": True  # Mark as independent configuration
                }
                
                # Check if model is supported
                if hasattr(self.llm, 'supported_models'):
                    model_info["supported"] = model_name in self.llm.supported_models
                    model_info["supported_models"] = self.llm.supported_models
                else:
                    model_info["supported"] = True
                
                # Add specific information based on model name
                if model_name == "glm-4-flash":
                    model_info.update({
                        "description": "Zhipu AI GLM-4-Flash model (retrieval planner specific)",
                        "version": "4.0",
                        "speed": "fast",
                        "cost": "low"
                    })
                elif model_name == "glm-z1-flash":
                    model_info.update({
                        "description": "Zhipu AI GLM-Z1-Flash model (retrieval planner specific)",
                        "version": "Z1",
                        "speed": "fast",
                        "cost": "free"
                    })
                
                return model_info
            else:
                return {
                    "status": "error",
                    "message": "LLM instance not properly initialized or missing configuration information"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to get model information: {str(e)}"
            }
        
    async def analyze_query_complexity(self, question: str, max_retries: int = 20) -> Tuple[int, List[str]]:
        """
        Analyze query complexity and extract keywords
        
        Args:
            question: User query question
            max_retries: Maximum number of retries
            
        Returns:
            Tuple[int, List[str]]: (Complexity level, Keywords list)
        """
        self.logger.info(f"Starting to analyze query complexity: {question}")
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Get prompt template
                prompt_template = self.prompt_manager.get_prompt("query_complexity_analysis")
                if not prompt_template:
                    raise ValueError("Unable to get query complexity analysis prompt")
                
                # Format prompt
                formatted_prompt = prompt_template.format(question=question)
                
                # Debug mode: show complete prompt
                if self.debug_mode:
                    self.logger.info(f"Complete prompt sent to LLM:\n{formatted_prompt}")
                
                # Build messages
                messages = [
                    self.llm.create_message(MessageRole.USER, formatted_prompt)
                ]
                
                # Call LLM (using already initialized instance)
                response = await self.llm.chat(messages)
                
                # Debug mode: show LLM raw response
                if self.debug_mode:
                    self.logger.info(f"LLM raw response: {response.content}")
                
                # Parse response
                complexity_level, keywords = self._parse_complexity_response(response.content)
                
                # ⚠️ Add detailed logging: verify complexity and expected category/strategy mapping
                category_map = {0: "FACTUAL", 1: "MIXED", 2: "INFERENTIAL"}
                strategy_map = {0: "simple", 1: "hybrid", 2: "complex"}
                expected_category = category_map.get(complexity_level, "UNKNOWN")
                expected_strategy = strategy_map.get(complexity_level, "unknown")
                
                self.logger.info(f"Query complexity analysis complete: {question}")
                self.logger.info(f"  → Complexity: {complexity_level}")
                self.logger.info(f"  → Keywords: {keywords}")
                self.logger.info(f"  → Expected category: {expected_category}")
                self.logger.info(f"  → Expected strategy: {expected_strategy}")
                
                return complexity_level, keywords
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Wait and retry
                    await asyncio.sleep(1 * (attempt + 1))  # Incremental delay
                    continue
        
        # All retries failed
        self.logger.error(f"All {max_retries} LLM calls failed, last error: {last_error}")
        raise RuntimeError(f"LLM retrieval planning call completely failed: {last_error}")
    
    def _parse_complexity_response(self, response: str) -> Tuple[int, List[str]]:
        """
        Parse LLM response to extract complexity level and keywords
        
        Args:
            response: LLM response content
            
        Returns:
            Tuple[int, List[str]]: (Complexity level, Keywords list)
        """
        # Clean response content
        response = response.strip()
        
        # Try to parse JSON format
        try:
            # Find JSON part
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                data = json.loads(json_str)
                
                complexity = data.get('complexity', 0)
                keywords = data.get('keywords', [])
                
                # Validate complexity level
                if complexity not in [0, 1, 2]:
                    raise ValueError(f"Invalid complexity level: {complexity}")
                
                # Validate keywords format
                if not isinstance(keywords, list):
                    keywords = []
                
                # Clean keywords
                cleaned_keywords = []
                for keyword in keywords:
                    if isinstance(keyword, str) and keyword.strip():
                        cleaned_keywords.append(keyword.strip().lower())
                
                return complexity, cleaned_keywords
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"JSON parsing failed, trying traditional parsing: {e}")
        
        # Traditional parsing method (backward compatible)
        complexity = 0
        keywords = []
        
        # Try direct number matching
        if response in ["0", "1", "2"]:
            complexity = int(response)
        else:
            # Find numbers 0, 1, 2 in response
            for char in response:
                if char in ["0", "1", "2"]:
                    complexity = int(char)
                    break
            
            # Try to match Chinese and English descriptions
            if complexity == 0:
                response_lower = response.lower()
                if any(word in response_lower for word in ["simple", "basic"]):
                    complexity = 0
                elif any(word in response_lower for word in ["mixed", "medium", "moderate"]):
                    complexity = 1
                elif any(word in response_lower for word in ["complex", "difficult", "advanced"]):
                    complexity = 2
        
        # If unable to parse, raise exception
        if complexity not in [0, 1, 2]:
            error_msg = f"Unable to parse LLM complexity response: {response}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        return complexity, keywords
    
    def _validate_prompt_template(self) -> None:
        """
        Validate if prompt template is available
        
        Raises:
            ValueError: If prompt template is unavailable
        """
        try:
            prompt_template = self.prompt_manager.get_prompt("query_complexity_analysis")
            if not prompt_template:
                raise ValueError("Query complexity analysis prompt template does not exist")
            
            # Test formatting
            test_question = "Test question"
            formatted_prompt = prompt_template.format(question=test_question)
            
            if "{question}" in formatted_prompt:
                raise ValueError("Prompt template formatting failed, question parameter not correctly replaced")
            
            self.logger.info("Prompt template validation successful")
            
        except Exception as e:
            error_msg = f"Prompt template validation failed: {e}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
    
    def get_prompt_template_info(self) -> Dict[str, Any]:
        """
        Get prompt template information
        
        Returns:
            Dict[str, Any]: Prompt template information
        """
        try:
            prompt_template = self.prompt_manager.get_prompt("query_complexity_analysis")
            if not prompt_template:
                return {"status": "error", "message": "Prompt template does not exist"}
            
            # Generate sample
            sample_question = "When did Caroline go to the LGBTQ support group?"
            formatted_sample = prompt_template.format(question=sample_question)
            
            return {
                "status": "success",
                "template_available": True,
                "sample_question": sample_question,
                "formatted_sample": formatted_sample,
                "template_length": len(formatted_sample)
            }
        except Exception as e:
            return {
                "status": "error", 
                "message": f"Failed to get prompt template information: {e}"
            }
    
    async def test_single_query(self, question: str, expected_complexity: Optional[int] = None) -> Dict[str, Any]:
        """
        Test analysis result of a single query
        
        Args:
            question: Test question
            expected_complexity: Expected complexity level (optional)
            
        Returns:
            Dict[str, Any]: Test result
        """
        try:
            # Enable debug mode for testing
            original_debug = self.debug_mode
            self.debug_mode = True
            
            complexity, keywords = await self.analyze_query_complexity(question)
            
            result = {
                "question": question,
                "predicted_complexity": complexity,
                "keywords": keywords,
                "complexity_description": QueryComplexityConfig.get_description(complexity),
                "success": True
            }
            
            if expected_complexity is not None:
                result["expected_complexity"] = expected_complexity
                result["match"] = complexity == expected_complexity
            
            # Restore original debug mode
            self.debug_mode = original_debug
            
            return result
            
        except Exception as e:
            return {
                "question": question,
                "error": str(e),
                "success": False
            }
    
    async def batch_analyze(self, questions: List[str], max_retries: int = 20) -> List[Tuple[int, List[str]]]:
        """
        Batch analyze query complexity and extract keywords
        
        Args:
            questions: List of query questions
            max_retries: Maximum retries for each query
            
        Returns:
            List[Tuple[int, List[str]]]: List of (complexity level, keywords list)
            
        Raises:
            RuntimeError: If any retrieval planning call fails
        """
        self.logger.info(f"Starting batch analysis of {len(questions)} queries")
        
        # Concurrent analysis, but limit concurrency to avoid overload
        semaphore = asyncio.Semaphore(3)  # Reduce concurrency for stability
        
        async def analyze_with_semaphore(question: str, index: int) -> tuple[int, Tuple[int, List[str]]]:
            async with semaphore:
                try:
                    result = await self.analyze_query_complexity(question, max_retries)
                    return index, result
                except Exception as e:
                    self.logger.error(f"Failed to analyze query {index}: {question} - {e}")
                    raise RuntimeError(f"Query '{question}' analysis failed: {e}")
        
        # Create tasks
        tasks = [analyze_with_semaphore(q, i) for i, q in enumerate(questions)]
        
        # Execute all tasks
        try:
            results = await asyncio.gather(*tasks)
            
            # Sort results by index
            sorted_results = sorted(results, key=lambda x: x[0])
            final_results = [result[1] for result in sorted_results]
            
            self.logger.info(f"Batch analysis complete, results: {[(r[0], len(r[1])) for r in final_results]}")
            return final_results
            
        except Exception as e:
            self.logger.error(f"Error occurred during batch analysis: {e}")
            raise


class QueryComplexityConfig:
    """Query complexity configuration"""
    
    # Complexity level definitions
    SIMPLE = 0
    MIXED = 1  
    COMPLEX = 2
    
    # Complexity descriptions
    COMPLEXITY_DESCRIPTIONS = {
        0: "Simple query",
        1: "Mixed query", 
        2: "Complex query"
    }
    
    @classmethod
    def get_description(cls, level: int) -> str:
        """Get complexity level description"""
        return cls.COMPLEXITY_DESCRIPTIONS.get(level, "Unknown complexity")
