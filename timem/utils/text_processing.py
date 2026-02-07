"""
TiMem Text Processing Tool
Provides text cleaning, tokenization, keyword extraction, summary generation and other functions
Based on LLM implementation, does not depend on traditional tokenization frameworks like jieba
"""

import re
import hashlib
import asyncio
from typing import List, Dict, Any, Optional, Union, Set
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from llm.base_llm import Message, MessageRole, ModelConfig
from llm.openai_adapter import OpenAIAdapter
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_llm_config


@dataclass
class TextInfo:
    """Text information data class"""
    original_text: str
    cleaned_text: str
    word_count: int
    char_count: int
    tokens: List[str]
    keywords: List[str]
    summary: str
    sentiment: Optional[str] = None
    language: Optional[str] = None
    hash_value: Optional[str] = None


class LLMTextProcessor:
    """LLM-based text processor"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or get_llm_config()
        self.logger = get_logger(__name__)
        
        # Initialize LLM adapter
        self._init_llm_adapter()
        
        # Common stopwords
        self.stop_words = {
            'the', 'and', 'a', 'an', 'is', 'in', 'it', 'of', 'to', 'that', 'this', 'for', 'with', 'as', 'on', 'at', 'by', 'from',
            'they', 'them', 'their', 'there', 'be', 'been', 'being', 'have', 'has', 'had', 'not', 'no', 'but', 'or', 'so', 'such',
            'what', 'which', 'when', 'where', 'why', 'how', 'can', 'could', 'may', 'might', 'shall', 'should', 'will', 'would',
            'I', 'me', 'my', 'mine', 'you', 'your', 'yours', 'he', 'him', 'his', 'she', 'her', 'hers', 'it', 'its', 'we', 'our',
            'ours', 'they', 'them', 'theirs', 'myself', 'yourself', 'himself', 'herself', 'itself', 'ourselves', 'yourselves',
            'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'doing', 'would', 'should', 'could', 'ought', 'i', 'you',
            'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their',
            'mine', 'yours', 'hers', 'ours', 'theirs', 'myself', 'yourself', 'himself', 'herself', 'itself', 'ourselves', 'yourselves',
            'themselves', 'now', 'then', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more',
            'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can',
            'will', 'just', 'don', 'should', 'now', 'too', 'very', 'can', 'will', 'just', 'don', 'should', 'now'
        }
        
        # English stopwords
        self.english_stop_words = {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'by', 'for', 'from', 'has', 'he',
            'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'will', 'with',
            'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours',
            'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
            'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves',
            'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are',
            'was', 'were', 'being', 'been', 'have', 'has', 'had', 'having', 'do', 'does', 'did',
            'doing', 'would', 'should', 'could', 'ought', 'im', 'youre', 'hes', 'shes', 'its',
            'were', 'theyre', 'ive', 'youve', 'weve', 'theyve', 'isnt', 'arent', 'wasnt',
            'werent', 'hasnt', 'havent', 'hadnt', 'wont', 'wouldnt', 'dont', 'doesnt', 'didnt',
            'cant', 'couldnt', 'shouldnt', 'mustnt', 'neednt', 'daren\'t', 'shan\'t', 'wont',
            'now', 'too', 'very', 'can', 'will', 'just', 'dont', 'should', 'now'
        }
        
        # Initialize TF-IDF vectorizer
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words=None,
            ngram_range=(1, 2),
            max_df=0.8,
            min_df=2
        )
        
        self.logger.info("LLM text processor initialization complete")
    
    def _init_llm_adapter(self):
        """Initialize LLM adapter"""
        try:
            # Use unified LLM manager to get adapter
            from llm.llm_manager import get_llm
            self.llm_adapter = get_llm()
            self.logger.info(f"Using LLM adapter: {type(self.llm_adapter).__name__}")
                
        except Exception as e:
            self.logger.error(f"LLM adapter initialization failed: {e}")
            self.llm_adapter = None
    
    def clean_text(self, text: str) -> str:
        """Clean text"""
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Remove email addresses
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', text)
        
        # Remove phone numbers
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep English, numbers and basic punctuation
        text = re.sub(r'[^\u0041-\u005a\u0061-\u007a\u0030-\u0039\u3002\uff1b\uff0c\uff1a\u201c\u201d\uff08\uff09\u3001\uff1f\uff01\u300a\u300b\s]', '', text)
        
        return text.strip()
    
    async def tokenize_with_llm(self, text: str, language: str = 'english') -> List[str]:
        """Tokenize using LLM"""
        if not text or not self.llm_adapter:
            return self._fallback_tokenize(text, language)
        
        try:
            if language == 'english':
                prompt = f"""Please tokenize the following English text, return only the tokens separated by spaces, exclude stop words:

Text: {text}

Tokens: """
            else:
                prompt = f"""Please tokenize the following text, return only the tokens separated by spaces, exclude stop words:

Text: {text}

Tokens: """
            
            response = await self.llm_adapter.complete(prompt, temperature=0.0)
            
            # Parse tokenization results
            tokens = [token.strip() for token in response.split() if token.strip()]
            
            # Filter stopwords
            if language == 'english':
                tokens = [token for token in tokens if token not in self.stop_words and len(token) > 2]
            
            return tokens
            
        except Exception as e:
            self.logger.warning(f"LLM tokenization failed, using rule-based tokenization: {e}")
            return self._fallback_tokenize(text, language)
    
    def _fallback_tokenize(self, text: str, language: str = 'english') -> List[str]:
        """Rule-based tokenization (fallback)"""
        if not text:
            return []
        
        if language == 'english':
            # English tokenization
            tokens = re.findall(r'\b\w+\b', text.lower())
        else:
            # Simple tokenization rules
            # Split by punctuation and spaces
            tokens = re.split(r'[，。！？；：""''（）【】《》、\\s]+', text)
            # Filter empty strings and short words
            tokens = [token.strip() for token in tokens if token.strip() and len(token.strip()) > 1]
        
        # Filter stopwords
        if language == 'english':
            tokens = [token for token in tokens if token not in self.stop_words and len(token) > 2]
        
        return tokens
    
    async def tokenize(self, text: str, language: str = 'english') -> List[str]:
        """Tokenization (async interface)"""
        return await self.tokenize_with_llm(text, language)
    
    async def extract_keywords_with_llm(self, text: str, top_k: int = 10) -> List[str]:
        """Extract keywords using LLM"""
        if not text or not self.llm_adapter:
            return self._fallback_extract_keywords(text, top_k)
        
        try:
            prompt = f"""Please extract the top {top_k} keywords from the following text, return only the keywords separated by commas:

Text: {text}

Keywords: """
            
            response = await self.llm_adapter.complete(prompt, temperature=0.1)
            
            # Parse keywords
            keywords = [kw.strip() for kw in response.split(',') if kw.strip()]
            
            return keywords[:top_k]
            
        except Exception as e:
            self.logger.warning(f"LLM keyword extraction failed, using rule-based extraction: {e}")
            return self._fallback_extract_keywords(text, top_k)
    
    def _fallback_extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """Rule-based keyword extraction (fallback)"""
        if not text:
            return []
        
        # Tokenization
        tokens = self._fallback_tokenize(text)
        
        if not tokens:
            return []
        
        # Use word frequency statistics
        word_freq = {}
        for token in tokens:
            word_freq[token] = word_freq.get(token, 0) + 1
        
        # Sort by frequency
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        
        # Return top_k keywords
        return [word for word, freq in sorted_words[:top_k]]
    
    async def extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """Extract keywords (async interface)"""
        return await self.extract_keywords_with_llm(text, top_k)
    
    async def extract_keywords_tfidf(self, texts: List[str], top_k: int = 10) -> List[List[str]]:
        """Extract keywords using TF-IDF"""
        if not texts:
            return []
        
        # Preprocess texts
        processed_texts = []
        for text in texts:
            tokens = await self.tokenize(text)
            processed_texts.append(' '.join(tokens))
        
        if not any(processed_texts):
            return [[] for _ in texts]
        
        # Calculate TF-IDF
        try:
            tfidf_matrix = self.tfidf_vectorizer.fit_transform(processed_texts)
            feature_names = self.tfidf_vectorizer.get_feature_names_out()
            
            keywords_list = []
            for i, text in enumerate(processed_texts):
                if not text.strip():
                    keywords_list.append([])
                    continue
                    
                # Get TF-IDF scores for this document
                tfidf_scores = tfidf_matrix[i].toarray()[0]
                
                # Get keywords with highest scores
                top_indices = np.argsort(tfidf_scores)[::-1][:top_k]
                keywords = [feature_names[idx] for idx in top_indices if tfidf_scores[idx] > 0]
                
                keywords_list.append(keywords)
            
            return keywords_list
        except Exception:
            # If TF-IDF fails, fallback to simple word frequency statistics
            return [await self.extract_keywords(text, top_k) for text in texts]
    
    async def generate_summary_with_llm(self, text: str, max_sentences: int = 3) -> str:
        """Generate summary using LLM"""
        if not text or not self.llm_adapter:
            return self._fallback_generate_summary(text, max_sentences)
        
        try:
            prompt = f"""Please generate a concise summary of the following text, limited to {max_sentences} sentences:

Text: {text}

Summary: """
            
            response = await self.llm_adapter.complete(prompt, temperature=0.3)
            
            return response.strip()
            
        except Exception as e:
            self.logger.warning(f"LLM summary generation failed, using rule-based generation: {e}")
            return self._fallback_generate_summary(text, max_sentences)
    
    def _fallback_generate_summary(self, text: str, max_sentences: int = 3) -> str:
        """Rule-based summary generation (fallback)"""
        if not text:
            return ""
        
        # Split into sentences
        sentences = self._split_sentences(text)
        
        if len(sentences) <= max_sentences:
            return text
        
        # Calculate sentence importance
        sentence_scores = self._calculate_sentence_scores(sentences)
        
        # Select sentences with highest scores
        top_sentences = sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True)[:max_sentences]
        
        # Sort by original order
        selected_sentences = sorted([sent for sent, score in top_sentences], key=sentences.index)
        
        return ''.join(selected_sentences)
    
    async def generate_summary(self, text: str, max_sentences: int = 3) -> str:
        """Generate summary (async interface)"""
        return await self.generate_summary_with_llm(text, max_sentences)
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split into sentences"""
        # English sentence splitting
        sentences = re.split(r'[.!?;]', text)
        
        # Filter empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def _calculate_sentence_scores(self, sentences: List[str]) -> Dict[str, float]:
        """Calculate sentence importance scores"""
        if not sentences:
            return {}
        
        # Calculate word frequency
        word_freq = {}
        for sentence in sentences:
            tokens = self._fallback_tokenize(sentence)
            for token in tokens:
                word_freq[token] = word_freq.get(token, 0) + 1
        
        # Calculate sentence scores
        sentence_scores = {}
        for sentence in sentences:
            tokens = self._fallback_tokenize(sentence)
            if tokens:
                score = sum(word_freq.get(token, 0) for token in tokens) / len(tokens)
                sentence_scores[sentence] = score
            else:
                sentence_scores[sentence] = 0.0
        
        return sentence_scores
    
    async def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity"""
        if not text1 or not text2:
            return 0.0
        
        # Tokenization
        tokens1 = set(await self.tokenize(text1))
        tokens2 = set(await self.tokenize(text2))
        
        if not tokens1 or not tokens2:
            return 0.0
        
        # Calculate Jaccard similarity
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        
        return intersection / union if union > 0 else 0.0
    
    async def calculate_cosine_similarity(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity"""
        if not text1 or not text2:
            return 0.0
        
        try:
            # Preprocess
            processed_text1 = ' '.join(await self.tokenize(text1))
            processed_text2 = ' '.join(await self.tokenize(text2))
            
            if not processed_text1 or not processed_text2:
                return 0.0
            
            # Calculate TF-IDF
            tfidf_matrix = self.tfidf_vectorizer.fit_transform([processed_text1, processed_text2])
            
            # Calculate cosine similarity
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            
            return similarity
        except Exception:
            # If calculation fails, fallback to Jaccard similarity
            return await self.calculate_similarity(text1, text2)
    
    def detect_language(self, text: str) -> str:
        """Detect language"""
        if not text:
            return 'unknown'
        
        # Count English characters
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        
        # Count digits
        digit_chars = len(re.findall(r'\d', text))
        
        total_chars = len(text)
        
        if total_chars == 0:
            return 'unknown'
        
        english_ratio = english_chars / total_chars
        
        if english_ratio > 0.5:
            return 'english'
        else:
            return 'mixed'
    
    def get_text_hash(self, text: str) -> str:
        """Get text hash value"""
        if not text:
            return ""
        
        # Calculate hash using SHA256
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    async def get_word_count(self, text: str) -> int:
        """Get word count"""
        if not text:
            return 0
        
        tokens = await self.tokenize(text)
        return len(tokens)
    
    def get_char_count(self, text: str) -> int:
        """Get character count"""
        if not text:
            return 0
        
        return len(text)
    
    async def extract_entities_with_llm(self, text: str) -> Dict[str, List[str]]:
        """Extract entities using LLM"""
        if not text or not self.llm_adapter:
            return self._fallback_extract_entities(text)
        
        try:
            prompt = f"""Please extract entities from the following text, return in the following JSON format:
{
    "person": ["name1", "name2"],
    "organization": ["org1", "org2"],
    "location": ["loc1", "loc2"],
    "date": ["date1", "date2"],
    "number": ["num1", "num2"]
}

Text: {text}

Entities: """
            
            response = await self.llm_adapter.complete(prompt, temperature=0.0)
            
            # Try to parse JSON
            try:
                import json
                entities = json.loads(response)
                return entities
            except json.JSONDecodeError:
                # If JSON parsing fails, use rule-based extraction
                return self._fallback_extract_entities(text)
            
        except Exception as e:
            self.logger.warning(f"LLM entity extraction failed, using rule-based extraction: {e}")
            return self._fallback_extract_entities(text)
    
    def _fallback_extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Rule-based entity extraction (fallback)"""
        if not text:
            return {}
        
        entities = {
            'person': [],
            'organization': [],
            'location': [],
            'date': [],
            'number': []
        }
        
        # Extract dates
        date_pattern = r'\d{4}[-/]\d{1,2}[-/]\d{1,2}'
        dates = re.findall(date_pattern, text)
        entities['date'].extend(dates)
        
        # Extract numbers
        number_pattern = r'\d+(?:\.\d+)?'
        numbers = re.findall(number_pattern, text)
        entities['number'].extend(numbers)
        
        # Simple English name recognition
        english_name_pattern = r'[A-Z][a-z]+ [A-Z][a-z]+'
        english_names = re.findall(english_name_pattern, text)
        entities['person'].extend(english_names)
        
        # Simple organization name recognition
        org_pattern = r'[A-Za-z]+(?: Inc| Ltd| Corp| Co)'
        orgs = re.findall(org_pattern, text)
        entities['organization'].extend(orgs)
        
        # Simple location name recognition
        location_pattern = r'[A-Za-z]+(?: City| Town| Village| County| State| Country)'
        locations = re.findall(location_pattern, text)
        entities['location'].extend(locations)
        
        # Deduplication
        for key in entities:
            entities[key] = list(set(entities[key]))
        
        return entities
    
    async def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract entities (async interface)"""
        return await self.extract_entities_with_llm(text)
    
    async def process_text(self, text: str, extract_keywords: bool = True, generate_summary: bool = True) -> TextInfo:
        """Process text and return complete information"""
        if not text:
            return TextInfo(
                original_text="",
                cleaned_text="",
                word_count=0,
                char_count=0,
                tokens=[],
                keywords=[],
                summary="",
                sentiment=None,
                language='unknown',
                hash_value=""
            )
        
        # Clean text
        cleaned_text = self.clean_text(text)
        
        # Tokenization
        tokens = await self.tokenize(cleaned_text)
        
        # Extract keywords
        keywords = await self.extract_keywords(cleaned_text) if extract_keywords else []
        
        # Generate summary
        summary = await self.generate_summary(cleaned_text) if generate_summary else ""
        
        # Detect language
        language = self.detect_language(cleaned_text)
        
        # Calculate hash value
        hash_value = self.get_text_hash(cleaned_text)
        
        return TextInfo(
            original_text=text,
            cleaned_text=cleaned_text,
            word_count=len(tokens),
            char_count=len(cleaned_text),
            tokens=tokens,
            keywords=keywords,
            summary=summary,
            sentiment=None,
            language=language,
            hash_value=hash_value
        )
    
    async def batch_process(self, texts: List[str], extract_keywords: bool = True, generate_summary: bool = True) -> List[TextInfo]:
        """Batch process texts"""
        if not texts:
            return []
        
        results = []
        for text in texts:
            result = await self.process_text(text, extract_keywords, generate_summary)
            results.append(result)
        
        return results
    
    def merge_texts(self, texts: List[str], separator: str = '\n') -> str:
        """Merge texts"""
        if not texts:
            return ""
        
        return separator.join(text for text in texts if text)
    
    def split_text(self, text: str, max_length: int = 1000, overlap: int = 100) -> List[str]:
        """Split text"""
        if not text or max_length <= 0:
            return []
        
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + max_length, len(text))
            
            # Try to split at sentence boundaries
            if end < len(text):
                # Find the nearest sentence ending
                sentence_end = max(
                    text.rfind('。', start, end),
                    text.rfind('！', start, end),
                    text.rfind('？', start, end),
                    text.rfind('.', start, end),
                    text.rfind('!', start, end),
                    text.rfind('?', start, end)
                )
                
                if sentence_end > start:
                    end = sentence_end + 1
            
            chunks.append(text[start:end])
            start = max(start + 1, end - overlap)
        
        return chunks


# For backward compatibility, keep the original class name
TextProcessor = LLMTextProcessor