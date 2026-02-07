"""
TiMem L1 Fragment-level Memory Implementation
Handles single-user-single-expert-single-session real-time memory fragment updates

Implementation Logic:
1. Fragment Division: Every n dialogue turns constitute one fragment
2. Progressive Fragment Summary: M_{F_l} = Summarize(λ·F_l ⊕ (1-λ)·M_{F_{l-1}})
3. Fragment Memory Generation: M_{F_k}^{(u_i, a_j)} = {M_{F_1}, M_{F_2}, ..., M_{F_{ceil(m/n)}}}
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, AsyncGenerator
import uuid  # Added import for uuid module

from timem.utils import time_utils
from timem.utils.text_processing import LLMTextProcessor
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_importance_scoring_config


@dataclass
class DialogueRecord:
    """Dialogue Record"""
    speaker: str
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = None

class L1FragmentMemory:
    """L1 Fragment-level Memory Processor"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.fragment_size = config.get("fragment_size", 2)  # Window size (dialogue turns, one sentence per party)
        self.merge_weight = config.get("merge_weight", 0.7)  # λ weight
        self.max_fragments = config.get("max_fragments", 100)
        
        # Use global configuration's historical memory limit, not L1-specific configuration
        from timem.utils.config_manager import get_app_config
        app_config = get_app_config()
        self.history_context_size = app_config.get("memory", {}).get("historical_memory_limit", 3)
        
        # Summary strategy selection
        self.summary_strategy = config.get("summary_strategy", "progressive")  # progressive | independent
        
        # Importance scoring configuration
        importance_config = get_importance_scoring_config()
        self.importance_enabled = importance_config.get("enabled", True)
        self.importance_default_score = importance_config.get("default_score", 0.0)
        self.importance_cache_enabled = importance_config.get("cache_enabled", True)
        self.importance_cache_ttl = importance_config.get("cache_ttl", 3600)
        
        # Importance scoring cache
        self.importance_cache = {}
        
        self.text_processor = LLMTextProcessor()
        self.logger = get_logger(__name__)
        
        # Initialize LLM adapter
        from llm.llm_manager import get_llm
        self.llm_adapter = get_llm()
        
        # Current session memory state
        self.current_fragments: List['L1FragmentMemory'] = []
        self.dialogue_buffer: List[DialogueRecord] = []
        self.session_summary: Optional[str] = None
        
        self.logger.info(f"Initialized L1 fragment-level memory processor, window size: {self.fragment_size} turns, historical context: {self.history_context_size} fragments (global config), summary strategy: {self.summary_strategy}")
        self.logger.info(f"Importance scoring feature: {'Enabled' if self.importance_enabled else 'Disabled'}")
    
    async def add_dialogue(self, speaker: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[List['L1FragmentMemory']]:
        """
        Add dialogue record, may trigger fragment generation
        
        Args:
            speaker: Speaker
            content: Dialogue content
            metadata: Metadata
            
        Returns:
            If new fragments are generated, return the list of newly generated fragments
        """
        # Create dialogue record
        dialogue = DialogueRecord(
            speaker=speaker,
            content=content,
            timestamp=time_utils.get_current_timestamp(),
            metadata=metadata or {}
        )
        
        self.dialogue_buffer.append(dialogue)
        self.logger.debug(f"Added dialogue record: {speaker} - {content[:50]}...")
        
        # Check if fragment generation condition is reached
        if len(self.dialogue_buffer) >= self.fragment_size:
            fragments = await self._generate_fragments()
            return fragments
        
        return None
    
    async def _generate_fragments(self) -> List['L1FragmentMemory']:
        """
        Generate memory fragments
        
        Returns:
            List of generated fragments
        """
        if not self.dialogue_buffer:
            raise ValueError("Dialogue buffer is empty, cannot generate fragments")
        
        fragments = []
        
        # Calculate number of fragments that can be generated
        total_dialogues = len(self.dialogue_buffer)
        num_fragments = total_dialogues // self.fragment_size
        
        self.logger.info(f"Generating {num_fragments} fragments, each fragment {self.fragment_size} turns")
        
        # Generate each fragment
        for i in range(num_fragments):
            start_idx = i * self.fragment_size
            end_idx = start_idx + self.fragment_size
            
            # Extract current fragment's dialogue
            fragment_dialogues = self.dialogue_buffer[start_idx:end_idx]
            
            # Generate fragment
            fragment = await self._create_fragment(fragment_dialogues, i)
            fragments.append(fragment)
            self.current_fragments.append(fragment)
        
        # Remove processed dialogues
        processed_count = num_fragments * self.fragment_size
        self.dialogue_buffer = self.dialogue_buffer[processed_count:]
        
        # Maintain fragment count limit
        if len(self.current_fragments) > self.max_fragments:
            self._merge_oldest_fragments()
        
        return fragments
    
    async def _create_fragment(self, dialogues: List[DialogueRecord], fragment_index: int) -> 'L1FragmentMemory':
        """
        Create a single memory fragment
        
        Args:
            dialogues: List of dialogue records
            fragment_index: Fragment index
            
        Returns:
            Memory fragment
        """
        # Merge dialogue content
        combined_content = self._combine_dialogues(dialogues)
        
        # Generate fragment summary
        fragment_summary = await self._generate_fragment_summary(combined_content, fragment_index)
        
        # Extract keywords and entities
        keywords = await self.text_processor.extract_keywords(combined_content)
        entities = await self._extract_entities(combined_content)
        
        # Calculate importance score
        importance_score = await self._calculate_importance(
            combined_content, keywords, entities
        )
        
        # Create fragment
        fragment = L1FragmentMemory(
            id=str(uuid.uuid4()),
            session_id="dummy_session_id", # Placeholder, needs actual session_id
            user_id="dummy_user_id", # Placeholder, needs actual user_id
            expert_id="dummy_expert_id", # Placeholder, needs actual expert_id
            start_time=time_utils.get_current_timestamp(),
            end_time=time_utils.get_current_timestamp(),
            dialogue_window=dialogues,
            summary=fragment_summary,
            importance=importance_score,
            level="L1"
        )
        
        if self.importance_enabled:
            self.logger.info(f"Generated fragment {fragment.id} (index: {fragment_index}), importance: {importance_score:.3f}")
        else:
            self.logger.info(f"Generated fragment {fragment.id} (index: {fragment_index}), importance scoring disabled")
        
        return fragment
    
    async def _generate_fragment_summary(self, content: str, fragment_index: int) -> str:
        """
        Generate fragment summary
        
        Args:
            content: Current fragment content
            fragment_index: Fragment index
            
        Returns:
            Fragment summary
        """
        # Get historical summary context
        history_summaries = self._get_history_context(fragment_index)
        
        print(f"\n🔄 Processing fragment {fragment_index + 1}:")
        print(f"📄 Original content (length: {len(content)} characters):")
        print(f"{'─' * 60}")
        print(content)
        print(f"{'─' * 60}")
        
        if fragment_index == 0:
            # First summary always uses independent window summary
            print(f"🔸 Using independent window summary (first summary)")
            summary = await self._independent_window_summarize(content)
        elif history_summaries and self.summary_strategy == "progressive":
            # Progressive window summary
            print(f"🔶 Using progressive window summary (historical context: {len(history_summaries)} fragments)")
            summary = await self._progressive_window_summarize(content, history_summaries)
        else:
            # Independent window summary (independent strategy)
            print(f"🔸 Using independent window summary")
            summary = await self._independent_window_summarize(content)
        
        print(f"📋 Generated summary (length: {len(summary)} characters, compression ratio: {len(summary)/len(content):.2%}):")
        print(f"  {summary}")
        print(f"{'═' * 80}")
        
        return summary
    
    def _get_history_context(self, current_index: int) -> List[str]:
        """
        Get historical summary context
        
        Historical summary count control logic:
        - If historical summaries are insufficient (e.g., can see 3 historical summaries but second summary can only see 1), use all
        - If historical summaries are sufficient (e.g., can see 3 historical summaries but 9th summary has 8 previous), only see latest 3
        
        Args:
            current_index: Current fragment index
            
        Returns:
            List of historical summaries
        """
        if current_index == 0:
            return []
        
        # Get most recent historical summaries, count not exceeding history_context_size
        start_idx = max(0, current_index - self.history_context_size)
        end_idx = current_index
        
        history_summaries = []
        for i in range(start_idx, end_idx):
            if i < len(self.current_fragments):
                history_summaries.append(self.current_fragments[i].summary)
        
        return history_summaries
    
    def _combine_dialogues(self, dialogues: List[DialogueRecord]) -> str:
        """Merge dialogue content - only includes speaker name and text, not timestamp"""
        combined = []
        for dialogue in dialogues:
            # Only include speaker and content, not timestamp
            combined.append(f"{dialogue.speaker}: {dialogue.content}")
        return "\n".join(combined)
    


    async def _independent_window_summarize(self, content: str) -> str:
        """
        Independent window summary: summarize based only on current window content
        
        Args:
            content: Window content
            
        Returns:
            Window summary
        """
        # Use LLM adapter for independent window summary
        prompt = f"""
Please provide a concise summary of the following dialogue content, extracting key information and main points:

Dialogue content:
{content}

Please generate a concise summary highlighting important information:
"""
        
        try:
            summary = await self.llm_adapter.generate_text(prompt)
            return summary.strip()
        except Exception as e:
            self.logger.error(f"Independent window summary generation failed: {e}")
            # Return simplified summary
            return f"Dialogue summary: {content[:100]}..."

    async def _progressive_window_summarize(self, current_content: str, history_summaries: List[str]) -> str:
        """
        Progressive window summary: first extract current window key information, then combine with historical background to generate summary
        
        Args:
            current_content: Current fragment content
            history_summaries: List of historical summaries
            
        Returns:
            Summary of current fragment
        """
        # Use LLM adapter for progressive window summary
        
        # Merge multiple historical summaries into background context
        if len(history_summaries) == 1:
            history_context = history_summaries[0]
        else:
            history_context = "\n".join([f"Fragment {i+1} summary: {summary}" for i, summary in enumerate(history_summaries)])
        
        prompt = f"""
Please generate a progressive summary based on historical background and current dialogue content:

Historical background:
{history_context}

Current dialogue content:
{current_content}

Please combine historical background and generate a progressive summary of current dialogue content, highlighting new information and changes:
"""
        
        try:
            summary = await self.llm_adapter.generate_text(prompt)
            return summary.strip()
        except Exception as e:
            self.logger.error(f"Progressive window summary generation failed: {e}")
            # Return simplified summary
            return f"Progressive summary: {current_content[:100]}..."
    

    
    async def _extract_entities(self, content: str) -> List[Dict[str, Any]]:
        """Extract entity information"""
        # Use text processor for entity extraction
        # Need to implement specific entity extraction logic here
        entities = []
        
        # Simplified implementation: identify entities based on keywords
        keywords = await self.text_processor.extract_keywords(content)
        for keyword in keywords[:10]:  # Limit entity count
            entity = {
                "text": keyword,
                "type": "KEYWORD",  # Can be extended to more specific types
                "confidence": 0.8,
                "start": content.find(keyword),
                "end": content.find(keyword) + len(keyword)
            }
            entities.append(entity)
        
        return entities
    
    async def _calculate_importance(self, content: str, keywords: List[str], entities: List[Dict[str, Any]]) -> float:
        """Calculate importance score"""
        
        # Check if importance scoring is enabled
        if not self.importance_enabled:
            self.logger.debug("Importance scoring feature disabled, using default score")
            return self.importance_default_score
        
        # Check cache
        if self.importance_cache_enabled:
            cache_key = f"{hash(content)}:{len(keywords)}:{len(entities)}"
            if cache_key in self.importance_cache:
                self.logger.debug("Retrieved importance score from cache")
                return self.importance_cache[cache_key]
        
        # Calculate importance based on multiple factors
        factors = {
            "content_length": min(len(content) / 1000, 1.0),  # Content length
            "keyword_density": min(len(keywords) / 20, 1.0),  # Keyword density
            "entity_count": min(len(entities) / 10, 1.0),     # Entity count
            "question_count": content.count("?") * 0.1,       # Question count
            "urgency_keywords": self._check_urgency_keywords(content),  # Urgency keywords
        }
        
        # Weighted calculation
        importance = (
            factors["content_length"] * 0.2 +
            factors["keyword_density"] * 0.3 +
            factors["entity_count"] * 0.2 +
            factors["question_count"] * 0.1 +
            factors["urgency_keywords"] * 0.2
        )
        
        final_score = min(importance, 1.0)
        
        # Cache result
        if self.importance_cache_enabled:
            cache_key = f"{hash(content)}:{len(keywords)}:{len(entities)}"
            self.importance_cache[cache_key] = final_score
            
            # Clean up expired cache
            if len(self.importance_cache) > 1000:  # Limit cache size
                self.importance_cache.clear()
        
        return final_score
    
    def _check_urgency_keywords(self, content: str) -> float:
        """Check urgency keywords"""
        urgency_keywords = ["important", "urgent", "immediately", "right now", "asap", "problem", "error", "failure"]
        count = sum(1 for keyword in urgency_keywords if keyword in content)
        return min(count * 0.2, 1.0)
    
    def _merge_oldest_fragments(self):
        """Merge oldest fragments to maintain count limit"""
        if len(self.current_fragments) < 2:
            return
        
        # Remove two oldest fragments
        oldest_fragment = self.current_fragments.pop(0)
        second_oldest = self.current_fragments.pop(0)
        
        # Merge fragments
        merged_content = f"{oldest_fragment.summary}\n\n{second_oldest.summary}"
        merged_keywords = list(set(oldest_fragment.summary.split() + second_oldest.summary.split()))
        merged_entities = oldest_fragment.entities + second_oldest.entities
        
        # Create merged fragment
        merged_fragment = L1FragmentMemory(
            id=str(uuid.uuid4()),
            session_id="dummy_session_id", # Placeholder
            user_id="dummy_user_id", # Placeholder
            expert_id="dummy_expert_id", # Placeholder
            start_time=oldest_fragment.start_time,
            end_time=second_oldest.end_time,
            dialogue_window=oldest_fragment.dialogue_window + second_oldest.dialogue_window,
            summary=f"Merged summary: {oldest_fragment.summary} | {second_oldest.summary}",
            importance=max(oldest_fragment.importance, second_oldest.importance),
            level="L1"
        )
        
        # Insert at beginning
        self.current_fragments.insert(0, merged_fragment)
        self.logger.info(f"Merged fragments {oldest_fragment.id} and {second_oldest.id} -> {merged_fragment.id}")
    
    async def generate_session_summary(self) -> str:
        """Generate session summary"""
        if not self.current_fragments:
            return "No dialogue content"
        
        # Merge all fragment summaries
        fragment_summaries = [f.summary for f in self.current_fragments]
        
        # Use memory generator for session-level summary
        from timem.memory.memory_generator import MemoryGenerator
        
        generator = MemoryGenerator()
        self.session_summary = await generator.generate_l2_content(fragment_summaries)
        return self.session_summary

    def clear_session(self):
        """Clear session state"""
        self.current_fragments.clear()
        self.dialogue_buffer.clear()
        self.session_summary = None
        self.logger.info("Session state cleared")

    async def generate_session_summary_with_comparison(self, independent_fragments: List['L1FragmentMemory'], progressive_fragments: List['L1FragmentMemory']) -> Dict[str, Any]:
        """
        Generate session summary comparison experiment
        
        Args:
            independent_fragments: List of fragments generated by independent window summary
            progressive_fragments: List of fragments generated by progressive window summary
            
        Returns:
            Session summary comparison results containing both strategies
        """
        from timem.memory.memory_generator import MemoryGenerator
        
        generator = MemoryGenerator()
        
        # 1. Session summary based on independent window summary
        independent_summaries = [f.summary for f in independent_fragments]
        independent_session_summary = await generator.generate_l2_content(independent_summaries)
        
        # 2. Session summary based on progressive window summary
        progressive_summaries = [f.summary for f in progressive_fragments]
        progressive_session_summary = await generator.generate_l2_content(progressive_summaries)
        
        # Analyze characteristics of both summaries
        comparison_result = {
            "independent_session_summary": {
                "content": independent_session_summary,
                "length": len(independent_session_summary),
                "fragment_count": len(independent_fragments),
                "avg_fragment_length": sum(len(f.summary) for f in independent_fragments) / len(independent_fragments) if independent_fragments else 0,
                "total_original_length": sum(len(f.summary) for f in independent_fragments), 
                "overall_compression_ratio": len(independent_session_summary) / sum(len(f.summary) for f in independent_fragments) if sum(len(f.summary) for f in independent_fragments) > 0 else 0,
                "source_strategy": "independent_window"
            },
            "progressive_session_summary": {
                "content": progressive_session_summary,
                "length": len(progressive_session_summary),
                "fragment_count": len(progressive_fragments),
                "avg_fragment_length": sum(len(f.summary) for f in progressive_fragments) / len(progressive_fragments) if progressive_fragments else 0,
                "total_original_length": sum(len(f.summary) for f in progressive_fragments), 
                "overall_compression_ratio": len(progressive_session_summary) / sum(len(f.summary) for f in progressive_fragments) if sum(len(f.summary) for f in progressive_fragments) > 0 else 0,
                "source_strategy": "progressive_window"
            },
            "comparison_metrics": {
                "length_difference": len(progressive_session_summary) - len(independent_session_summary),
                "compression_ratio_difference": 0,
                "coherence_analysis": await self._analyze_summary_coherence(independent_session_summary, progressive_session_summary),
                "information_density_comparison": await self._compare_information_density(independent_session_summary, progressive_session_summary, independent_fragments, progressive_fragments)
            }
        }
        
        # Calculate compression ratio difference
        if comparison_result["independent_session_summary"]["overall_compression_ratio"] > 0:
            comparison_result["comparison_metrics"]["compression_ratio_difference"] = (
                comparison_result["progressive_session_summary"]["overall_compression_ratio"] - 
                comparison_result["independent_session_summary"]["overall_compression_ratio"]
            )
        
        return comparison_result

    async def _analyze_summary_coherence(self, independent_summary: str, progressive_summary: str) -> Dict[str, Any]:
        """
        Analyze coherence of two session summaries
        
        Args:
            independent_summary: Session summary generated by independent window strategy
            progressive_summary: Session summary generated by progressive window strategy
            
        Returns:
            Coherence analysis results
        """
        # Simplified coherence analysis
        coherence_analysis = {
            "independent_word_count": len(independent_summary.split()),
            "progressive_word_count": len(progressive_summary.split()),
            "independent_sentence_count": len([s for s in independent_summary.split('.') if s.strip()]),
            "progressive_sentence_count": len([s for s in progressive_summary.split('.') if s.strip()]),
            "word_overlap_ratio": 0,
            "sentence_structure_comparison": {
                "independent_avg_sentence_length": 0,
                "progressive_avg_sentence_length": 0
            }
        }
        
        # Calculate word overlap ratio
        independent_words = set(independent_summary.split())
        progressive_words = set(progressive_summary.split())
        if independent_words:
            coherence_analysis["word_overlap_ratio"] = len(independent_words.intersection(progressive_words)) / len(independent_words.union(progressive_words))
        
        # Calculate average sentence length
        independent_sentences = [s.strip() for s in independent_summary.split('.') if s.strip()]
        progressive_sentences = [s.strip() for s in progressive_summary.split('.') if s.strip()]
        
        if independent_sentences:
            coherence_analysis["sentence_structure_comparison"]["independent_avg_sentence_length"] = sum(len(s) for s in independent_sentences) / len(independent_sentences)
        
        if progressive_sentences:
            coherence_analysis["sentence_structure_comparison"]["progressive_avg_sentence_length"] = sum(len(s) for s in progressive_sentences) / len(progressive_sentences)
        
        return coherence_analysis

    async def _compare_information_density(self, independent_summary: str, progressive_summary: str, 
                                         independent_fragments: List['L1FragmentMemory'], progressive_fragments: List['L1FragmentMemory']) -> Dict[str, Any]:
        """
        Compare information density of two session summaries
        
        Args:
            independent_summary: Session summary generated by independent window strategy
            progressive_summary: Session summary generated by progressive window strategy
            independent_fragments: Independent window summary fragments
            progressive_fragments: Progressive window summary fragments
            
        Returns:
            Information density comparison results
        """
        # Collect all keywords and entities
        independent_keywords = set()
        progressive_keywords = set()
        independent_entities = set()
        progressive_entities = set()
        
        for fragment in independent_fragments:
            independent_keywords.update(fragment.summary.split()) 
            for entity in fragment.entities:
                independent_entities.add(entity.get("text", ""))
        
        for fragment in progressive_fragments:
            progressive_keywords.update(fragment.summary.split()) 
            for entity in fragment.entities:
                progressive_entities.add(entity.get("text", ""))
        
        # Analyze information density
        density_comparison = {
            "independent_strategy": {
                "keyword_density": len(independent_keywords) / len(independent_summary) if independent_summary else 0,
                "entity_density": len(independent_entities) / len(independent_summary) if independent_summary else 0,
                "keyword_coverage_in_summary": 0,
                "entity_coverage_in_summary": 0
            },
            "progressive_strategy": {
                "keyword_density": len(progressive_keywords) / len(progressive_summary) if progressive_summary else 0,
                "entity_density": len(progressive_entities) / len(progressive_summary) if progressive_summary else 0,
                "keyword_coverage_in_summary": 0,
                "entity_coverage_in_summary": 0
            }
        }
        
        # Calculate keyword and entity coverage in summary
        if independent_keywords:
            covered_keywords = sum(1 for keyword in independent_keywords if keyword in independent_summary)
            density_comparison["independent_strategy"]["keyword_coverage_in_summary"] = covered_keywords / len(independent_keywords)
        
        if independent_entities:
            covered_entities = sum(1 for entity in independent_entities if entity and entity in independent_summary)
            density_comparison["independent_strategy"]["entity_coverage_in_summary"] = covered_entities / len(independent_entities)
        
        if progressive_keywords:
            covered_keywords = sum(1 for keyword in progressive_keywords if keyword in progressive_summary)
            density_comparison["progressive_strategy"]["keyword_coverage_in_summary"] = covered_keywords / len(progressive_keywords)
        
        if progressive_entities:
            covered_entities = sum(1 for entity in progressive_entities if entity and entity in progressive_summary)
            density_comparison["progressive_strategy"]["entity_coverage_in_summary"] = covered_entities / len(progressive_entities)
        
        return density_comparison
    
    async def process_session_stream(self, dialogues: List[DialogueRecord]) -> AsyncGenerator['L1FragmentMemory', None]:
        """
        Process session in streaming mode, yield each generated fragment
        
        Args:
            dialogues: List of dialogue records
            
        Yields:
            Generated memory fragments
        """
        self.clear_session()
        self.dialogue_buffer = list(dialogues)
        
        total_dialogues = len(self.dialogue_buffer)
        num_fragments = (total_dialogues + self.fragment_size - 1) // self.fragment_size
        
        self.logger.info(f"Starting streaming session processing: {total_dialogues} dialogue turns, estimated {num_fragments} fragments to generate")
        
        for i in range(num_fragments):
            start_idx = i * self.fragment_size
            end_idx = start_idx + self.fragment_size
            
            if start_idx >= len(self.dialogue_buffer):
                break
                
            fragment_dialogues = self.dialogue_buffer[start_idx:end_idx]
            
            # Generate and yield fragment
            fragment = await self._create_fragment(fragment_dialogues, i)
            self.current_fragments.append(fragment)
            yield fragment
    
    async def process_complete_session(self, dialogues: List[DialogueRecord]) -> List['L1FragmentMemory']:
        """
        Process entire session at once, return all generated memory fragments
        
        Args:
            dialogues: List of dialogue records
            
        Returns:
            List of generated memory fragments
        """
        fragments = []
        async for fragment in self.process_session_stream(dialogues):
            fragments.append(fragment)
        return fragments

    async def process_complete_session_with_comparison(self, dialogues: List[DialogueRecord]) -> Dict[str, List['L1FragmentMemory']]:
        """
        Process all dialogues of complete session, simultaneously generate independent window summaries and progressive summaries for comparison
        
        Args:
            dialogues: Complete list of dialogue records
            
        Returns:
            Dictionary containing results of different summary strategies
        """
        # Clear current state
        self.current_fragments.clear()
        self.dialogue_buffer.clear()
        
        # Batch add dialogues
        for dialogue in dialogues:
            self.dialogue_buffer.append(dialogue)
        
        # Generate all possible fragments
        total_dialogues = len(self.dialogue_buffer)
        num_fragments = total_dialogues // self.fragment_size
        
        self.logger.info(f"Comparison experiment: processing complete session, {total_dialogues} dialogue turns, generating {num_fragments} fragments")
        
        # Results dictionary
        results = {
            "independent_summaries": [],
            "progressive_summaries": []
        }
        
        # Generate two types of summaries for each fragment
        for i in range(num_fragments):
            start_idx = i * self.fragment_size
            end_idx = start_idx + self.fragment_size
            
            # Extract dialogues for current fragment
            fragment_dialogues = self.dialogue_buffer[start_idx:end_idx]
            combined_content = self._combine_dialogues(fragment_dialogues)
            
            # Get history summary context
            history_summaries = self._get_history_context(i)
            
            print(f"\n Comparison experiment - Processing fragment {i + 1}:")
            print(f" Original content (length: {len(combined_content)} characters):")
            print(f"{'─' * 60}")
            print(combined_content)
            print(f"{'─' * 60}")
            
            # 1. Independent window summary
            print(f" Generating independent window summary...")
            independent_summary = await self._independent_window_summarize(combined_content)
            print(f" Independent window summary (length: {len(independent_summary)} characters, compression ratio: {len(independent_summary)/len(combined_content):.2%}):")
            print(f"  {independent_summary}")
            
            # 2. Progressive window summary
            if i == 0:
                # First summary always uses independent window summary
                print(f" Generating progressive window summary (first summary, using independent summary)...")
                progressive_summary = await self._independent_window_summarize(combined_content)
            elif history_summaries:
                print(f" Generating progressive window summary (history context: {len(history_summaries)} fragments)...")
                progressive_summary = await self._progressive_window_summarize(combined_content, history_summaries)
            else:
                print(f" Generating progressive window summary (no history context, using independent summary)...")
                progressive_summary = await self._independent_window_summarize(combined_content)
            
            print(f" Progressive window summary (length: {len(progressive_summary)} characters, compression ratio: {len(progressive_summary)/len(combined_content):.2%}):")
            print(f"  {progressive_summary}")
            print(f"{'═' * 80}")
            
            # Create fragment (using independent window summary as base)
            fragment = L1FragmentMemory(
                id=str(uuid.uuid4()),
                session_id="dummy_session_id", # Placeholder
                user_id="dummy_user_id", # Placeholder
                expert_id="dummy_expert_id", # Placeholder
                start_time=time_utils.get_current_timestamp(),
                end_time=time_utils.get_current_timestamp(),
                dialogue_window=fragment_dialogues,
                summary=independent_summary,
                importance=await self._calculate_importance(
                    combined_content, 
                    await self.text_processor.extract_keywords(combined_content),
                    await self._extract_entities(combined_content)
                ),
                level="L1"
            )
            
            results["independent_summaries"].append(fragment)
            
            # Create progressive version
            fragment_progressive = L1FragmentMemory(
                id=str(uuid.uuid4()),
                session_id="dummy_session_id", # Placeholder
                user_id="dummy_user_id", # Placeholder
                expert_id="dummy_expert_id", # Placeholder
                start_time=time_utils.get_current_timestamp(),
                end_time=time_utils.get_current_timestamp(),
                dialogue_window=fragment_dialogues,
                summary=progressive_summary,
                importance=await self._calculate_importance(
                    combined_content, 
                    await self.text_processor.extract_keywords(combined_content),
                    await self._extract_entities(combined_content)
                ),
                level="L1"
            )
            
            results["progressive_summaries"].append(fragment_progressive)
            
            # Add to current fragment list (for history context of next fragment)
            self.current_fragments.append(fragment_progressive)  # Use progressive version as history context
        
        return results
    
    def get_session_state(self) -> Dict[str, Any]:
        """Get current session state"""
        return {
            "fragment_count": len(self.current_fragments),
            "dialogue_buffer_size": len(self.dialogue_buffer),
            "session_summary": self.session_summary,
            "total_importance": sum(f.importance for f in self.current_fragments), # Changed from importance_score to importance
            "window_size": self.fragment_size,
            "history_context_size": self.history_context_size,
            "fragments": [
                {
                    "id": f.id,
                    "index": f.fragment_index, # This will be 0 for all fragments in this new structure
                    "summary": f.summary,
                    "importance": f.importance,
                    "created_at": f.start_time.isoformat(), # Changed from created_at to start_time
                    "dialogue_count": len(f.dialogue_window) # Changed from raw_dialogues to dialogue_window
                }
                for f in self.current_fragments
            ]
        }
    
    def clear_session(self):
        """Clear session state"""
        self.current_fragments.clear()
        self.dialogue_buffer.clear()
        self.session_summary = None
        self.logger.info("Session state cleared")
    
    async def search_fragments(self, query: str, top_k: int = 5) -> List[Tuple['L1FragmentMemory', float]]:
        """Search for relevant fragments"""
        if not self.current_fragments:
            return []
        
        results = []
        for fragment in self.current_fragments:
            # Calculate similarity
            similarity = self.text_processor.calculate_similarity(query, fragment.summary) # Changed from content to summary
            if similarity > 0.3:  # Similarity threshold
                results.append((fragment, similarity))
        
        # Sort by similarity
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    async def process_fragments(self, fragments: List[DialogueRecord]) -> 'L1FragmentMemory':
        """Process fragments, generate memory fragments
        
        Args:
            fragments: List of dialogue records
            
        Returns:
            Memory fragment object
        """
        try:
            # Combine dialogue content
            combined_content = self._combine_dialogues(fragments)
            
            # Generate summary
            summary = await self._generate_fragment_summary(combined_content, 0)
            
            # Extract keywords
            keywords = await self.text_processor.extract_keywords(combined_content)
            
            # Extract entities
            entities = await self._extract_entities(combined_content)
            
            # Calculate importance
            importance_score = await self._calculate_importance(combined_content, keywords, entities)
            
            # Create memory fragment
            memory_fragment = L1FragmentMemory(
                id=str(uuid.uuid4()),
                session_id="dummy_session_id", # Placeholder
                user_id="dummy_user_id", # Placeholder
                expert_id="dummy_expert_id", # Placeholder
                start_time=time_utils.get_current_timestamp(),
                end_time=time_utils.get_current_timestamp(),
                dialogue_window=fragments,
                summary=summary,
                importance=importance_score,
                level="L1"
            )
            
            self.logger.info(f"Processed fragment, dialogue count: {len(fragments)}, importance: {importance_score}")
            return memory_fragment
            
        except Exception as e:
            self.logger.error(f"Failed to process fragment: {e}")
            # Return default memory fragment
            return L1FragmentMemory(
                id=str(uuid.uuid4()),
                session_id="dummy_session_id", # Placeholder
                user_id="dummy_user_id", # Placeholder
                expert_id="dummy_expert_id", # Placeholder
                start_time=time_utils.get_current_timestamp(),
                end_time=time_utils.get_current_timestamp(),
                dialogue_window=fragments,
                summary="Failed to process",
                importance=0.5,
                level="L1"
            )
    
    async def process_fragments_with_history(self, fragments: List[DialogueRecord], history_memories: List[Any]) -> 'L1FragmentMemory':
        """Process fragments, use history memories for progressive summarization
        
        Args:
            fragments: List of dialogue records
            history_memories: List of history memories (retrieved from database)
            
        Returns:
            Memory fragment object
        """
        try:
            # Combine dialogue content
            combined_content = self._combine_dialogues(fragments)
            
            # Generate progressive summary
            if history_memories:
                # Build history context
                history_context = []
                for hist_memory in history_memories[-3:]:  # Last 3 memory fragments
                    if hasattr(hist_memory, 'summary'):
                        history_context.append(f"History memory: {hist_memory.summary}")
                    elif isinstance(hist_memory, dict) and 'summary' in hist_memory:
                        history_context.append(f"History memory: {hist_memory['summary']}")
                
                # Use progressive summary
                summary = await self._progressive_window_summarize(combined_content, history_context)
                self.logger.info(f"Using progressive summary, history memory count: {len(history_memories)}")
            else:
                # Use independent window summary
                summary = await self._independent_window_summarize(combined_content)
                self.logger.info("Using independent window summary")
            
            # Extract keywords
            keywords = await self.text_processor.extract_keywords(combined_content)
            
            # Extract entities
            entities = await self._extract_entities(combined_content)
            
            # Calculate importance
            importance_score = await self._calculate_importance(combined_content, keywords, entities)
            
            # Create memory fragment
            memory_fragment = L1FragmentMemory(
                id=str(uuid.uuid4()),
                session_id="dummy_session_id",
                user_id="dummy_user_id",
                expert_id="dummy_expert_id",
                start_time=time_utils.get_current_timestamp(),
                end_time=time_utils.get_current_timestamp(),
                dialogue_window=fragments,
                summary=summary,
                importance=importance_score,
                level="L1"
            )
            
            self.logger.info(f"Fragment processing completed, dialogue count: {len(fragments)}, importance: {importance_score}")
            return memory_fragment
            
        except Exception as e:
            self.logger.error(f"Fragment processing failed: {e}")
            return L1FragmentMemory(
                id=str(uuid.uuid4()),
                session_id="dummy_session_id",
                user_id="dummy_user_id",
                expert_id="dummy_expert_id",
                start_time=time_utils.get_current_timestamp(),
                end_time=time_utils.get_current_timestamp(),
                dialogue_window=fragments,
                summary="Processing failed",
                importance=0.5,
                level="L1"
            )