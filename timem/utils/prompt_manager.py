"""
TiMem Prompt Management Module
Responsible for loading and managing prompts in prompts.yaml.
"""
import os
from typing import Dict, Any, Optional

from langchain_core.prompts import PromptTemplate

from .config_manager import get_config
from .logging import get_logger

logger = get_logger(__name__)

class PromptManager:
    """
    A singleton class for loading and managing prompts.
    Can provide corresponding prompt templates based on language options in global config.
    """
    _instance = None
    _prompts: Optional[Dict[str, Any]] = None
    _language: str = "en"

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PromptManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton instance for re-initialization"""
        cls._instance = None

    def _initialize(self):
        """Initialize and load config and prompts."""
        try:
            app_config = get_config("app")
            self._language = app_config.get("language", "en")
            
            prompt_config = get_config("prompts")
            if not prompt_config:
                raise FileNotFoundError("prompts.yaml not found or is empty.")
            self._prompts = prompt_config
            logger.info(f"Prompt module initialized successfully, current language: {self._language.upper()}")
        except Exception as e:
            logger.error(f"Prompt module initialization failed: {e}", exc_info=True)
            self._prompts = {}
    
    def reload_prompts(self):
        """Reload prompt config, support dataset-specific config"""
        try:
            from .config_manager import get_config_manager
            # Reload config manager
            config_manager = get_config_manager()
            config_manager.reload_config()
            
            # Reload prompt config
            prompt_config = get_config("prompts")
            if not prompt_config:
                logger.warning("Prompt config is empty after reload")
                return False
            
            self._prompts = prompt_config
            logger.info(f"Prompt config reloaded, current language: {self._language.upper()}")
            return True
        except Exception as e:
            logger.error(f"Failed to reload prompt config: {e}", exc_info=True)
            return False

    def get_prompt(self, key: str, **kwargs) -> Optional[PromptTemplate]:
        """
        Get formatted prompt template by key.

        Args:
            key (str): Key of prompt in YAML file.
            **kwargs: Variables to fill template.

        Returns:
            Optional[PromptTemplate]: LangChain prompt template object, or None if key not found.
        """
        if not self._prompts:
            logger.error("Prompt config not loaded, attempting to reload...")
            if not self.reload_prompts():
                logger.error("Failed to reload prompt config, cannot get prompt.")
                return None
            
        prompt_data = self._prompts.get(key)
        if not prompt_data:
            logger.warning(f"Prompt not found: '{key}', attempting to reload config...")
            if self.reload_prompts():
                prompt_data = self._prompts.get(key)
                if not prompt_data:
                    logger.error(f"Prompt not found after reload: '{key}'")
                    return None
            else:
                logger.error(f"Failed to reload config, cannot get prompt: '{key}'")
                return None

        template_str = prompt_data.get(self._language)
        if not template_str:
            logger.warning(f"Language '{self._language}' version not found for prompt '{key}', trying English version.")
            template_str = prompt_data.get("en")

        if not template_str:
            logger.error(f"English version also not found for prompt '{key}', cannot create template.")
            return None
        
        # Use safe=True to allow partial variable missing
        prompt_template = PromptTemplate.from_template(template_str)
        
        if kwargs:
            try:
                # This is an optional step, usually we only return the template.
                # formatted_prompt = prompt_template.format(**kwargs)
                # return formatted_prompt
                pass
            except KeyError as e:
                logger.error(f"Missing variable when formatting prompt '{key}': {e}")
                return None

        return prompt_template

    def set_language(self, language: str):
        """Dynamically switch language."""
        self._language = language
        logger.info(f"Prompt language switched to: {language.upper()}")
    
    def debug_prompt_keys(self) -> Dict[str, Any]:
        """
        Return debug information of currently loaded prompt config.
        
        Returns:
            Dict[str, Any]: Dictionary with current language, total prompts count and available keys
        """
        if not self._prompts:
            return {
                "current_language": self._language,
                "total_prompts": 0,
                "available_keys": []
            }
        
        return {
            "current_language": self._language,
            "total_prompts": len(self._prompts),
            "available_keys": list(self._prompts.keys())
        }

# Provide a global access point
def get_prompt_manager() -> PromptManager:
    """Get singleton instance of PromptManager."""
    return PromptManager()

def reload_prompt_manager():
    """Force reload prompt manager, support dataset-specific config"""
    PromptManager.reset_instance()
    return get_prompt_manager()

# Example usage
if __name__ == '__main__':
    # Assume your config/settings.yaml has app: language: "zh"
    # and config/prompts.yaml has been created
    
    # First call will initialize
    prompt_manager = get_prompt_manager()

    # Get Chinese prompt for L1 fragment summary
    l1_prompt_template = prompt_manager.get_prompt("l1_fragment_summary")
    if l1_prompt_template:
        formatted_prompt = l1_prompt_template.format(
            previous_summary="User asked about pricing.",
            new_dialogue="Expert answered the pricing question and recommended Plan B."
        )
        print("--- L1 Chinese Prompt ---")
        print(formatted_prompt)

    # Switch language
    prompt_manager.set_language("en")

    # Get English prompt for L1 fragment summary
    l1_prompt_template_en = prompt_manager.get_prompt("l1_fragment_summary")
    if l1_prompt_template_en:
        formatted_prompt_en = l1_prompt_template_en.format(
            previous_summary="User asked about pricing.",
            new_dialogue="Expert answered the pricing question and recommended Plan B."
        )
        print("\n--- L1 English Prompt ---")
        print(formatted_prompt_en)

    # Get a non-existent prompt
    non_existent_prompt = prompt_manager.get_prompt("non_existent_key")
    print(f"\nGetting non-existent prompt: {non_existent_prompt}")