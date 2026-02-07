"""
Chinese tokenization tool module
Provides high-quality Chinese tokenization support for PostgreSQL full-text search
"""

import re
from typing import List, Optional, Set
import jieba
import jieba.posseg as pseg
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ChineseTokenizer:
    """
    Chinese tokenizer
    
    Used to tokenize Chinese text so that PostgreSQL's tsvector can correctly index and retrieve Chinese content
    """
    
    def __init__(self, use_paddle: bool = False):
        """
        Initialize Chinese tokenizer
        
        Args:
            use_paddle: Whether to use PaddlePaddle mode (more accurate but requires additional dependencies)
        """
        self.use_paddle = use_paddle
        
        # Initialize jieba
        if use_paddle:
            try:
                jieba.enable_paddle()
                logger.info("✅ PaddlePaddle tokenization mode enabled")
            except Exception as e:
                logger.warning(f"PaddlePaddle mode initialization failed, using default mode: {e}")
                self.use_paddle = False
        
        # Chinese stopwords list
        self.stop_words = self._load_stop_words()
        
        # POS filtering (keep content words, filter function words)
        self.keep_pos = {'n', 'v', 'a', 'i', 'j', 'l', 'ns', 'nt', 'nz', 'vn', 'an'}  # nouns, verbs, adjectives, etc.
        
        logger.info(f"✅ Chinese tokenizer initialization complete (use_paddle={self.use_paddle})")
    
    def _load_stop_words(self) -> Set[str]:
        """Load Chinese stopwords"""
        # Common Chinese stopwords
        stop_words = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
            '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
            '自己', '这', '那', '里', '就是', '为', '以', '时候', '个', '等', '能', '可以',
            '这个', '什么', '他', '她', '它', '们', '我们', '你们', '他们', '她们', '它们',
            '吗', '呢', '吧', '啊', '哦', '嗯', '哈', '呀', '啦', '哪', '吗', '呢', '吧',
            '、', '，', '。', '！', '？', '；', '：', '"', '"', ''', ''', '（', '）', '【', '】',
            '《', '》', '—', '…', '·', '「', '」', '『', '』', '～', '＃', '＆', '＊', '＋'
        }
        return stop_words
    
    def tokenize(self, text: str, 
                 remove_stopwords: bool = True, 
                 keep_english: bool = True,
                 min_word_len: int = 1) -> List[str]:
        """
        Tokenize text
        
        Args:
            text: Input text
            remove_stopwords: Whether to remove stopwords
            keep_english: Whether to keep English words
            min_word_len: Minimum word length (number of characters)
            
        Returns:
            List of tokenization results
        """
        if not text or not text.strip():
            return []
        
        # Preprocess: clean special characters
        text = self._preprocess(text)
        
        # Tokenize
        if self.use_paddle:
            words = jieba.cut(text, use_paddle=True)
        else:
            words = jieba.cut(text)
        
        # Filter and clean
        tokens = []
        for word in words:
            word = word.strip()
            
            # Skip empty words
            if not word:
                continue
            
            # Skip words that are too short
            if len(word) < min_word_len:
                continue
            
            # Detect if it's a Chinese word
            is_chinese = self._is_chinese(word)
            is_english = self._is_english(word)
            
            # Keep Chinese words
            if is_chinese:
                if remove_stopwords and word in self.stop_words:
                    continue
                tokens.append(word)
            
            # Keep English words based on settings
            elif is_english and keep_english:
                if remove_stopwords and word.lower() in self.stop_words:
                    continue
                tokens.append(word.lower())
            
            # Keep numbers
            elif word.isdigit() or self._is_mixed_alphanumeric(word):
                tokens.append(word)
        
        return tokens
    
    def tokenize_for_postgres(self, text: str) -> str:
        """
        Tokenize for PostgreSQL and return space-separated string
        
        This is the core method for generating PostgreSQL tsvector-compatible text
        
        Args:
            text: Original text
            
        Returns:
            Space-separated tokenization result string
        """
        tokens = self.tokenize(
            text, 
            remove_stopwords=True,  # Remove stopwords to improve retrieval quality
            keep_english=True,      # Keep English words to support mixed Chinese-English
            min_word_len=1          # Keep single-character words (meaningful in Chinese)
        )
        
        # Join with spaces for PostgreSQL to_tsvector use
        result = ' '.join(tokens)
        
        logger.debug(f"Tokenization result: {text[:50]}... -> {result[:100]}...")
        
        return result
    
    def tokenize_with_pos(self, text: str, 
                         remove_stopwords: bool = True) -> List[tuple]:
        """
        Tokenize with POS tagging
        
        Args:
            text: Input text
            remove_stopwords: Whether to remove stopwords
            
        Returns:
            List of [(word, POS), ...]
        """
        if not text or not text.strip():
            return []
        
        text = self._preprocess(text)
        
        # POS tagging
        words_with_pos = pseg.cut(text)
        
        # Filter
        tokens = []
        for word, pos in words_with_pos:
            word = word.strip()
            
            if not word or len(word) < 1:
                continue
            
            # Keep only content words
            if pos[0] in self.keep_pos:
                if remove_stopwords and word in self.stop_words:
                    continue
                tokens.append((word, pos))
        
        return tokens
    
    def extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """
        Extract keywords
        
        Args:
            text: Input text
            top_k: Return top k keywords
            
        Returns:
            List of keywords
        """
        import jieba.analyse
        
        if not text or not text.strip():
            return []
        
        # Extract keywords using TF-IDF
        keywords = jieba.analyse.extract_tags(text, topK=top_k, withWeight=False)
        
        return keywords
    
    def _preprocess(self, text: str) -> str:
        """Preprocess text"""
        if not text:
            return ""
        
        # Keep Chinese, English, numbers, and spaces
        # Replace other characters with spaces (maintain word separation)
        text = re.sub(r'[^\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9\s]', ' ', text)
        
        # Merge multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _is_chinese(self, word: str) -> bool:
        """Check if it's a Chinese word"""
        if not word:
            return False
        # Contains at least one Chinese character
        return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', word))
    
    def _is_english(self, word: str) -> bool:
        """Check if it's an English word"""
        if not word:
            return False
        return bool(re.match(r'^[a-zA-Z]+$', word))
    
    def _is_mixed_alphanumeric(self, word: str) -> bool:
        """Check if it's alphanumeric mixed"""
        if not word:
            return False
        return bool(re.match(r'^[a-zA-Z0-9]+$', word))
    
    def add_user_dict(self, dict_path: str):
        """
        Add user-defined dictionary
        
        Args:
            dict_path: Path to dictionary file
        """
        try:
            jieba.load_userdict(dict_path)
            logger.info(f"✅ User dictionary loaded: {dict_path}")
        except Exception as e:
            logger.error(f"❌ Failed to load user dictionary: {e}")
    
    def add_word(self, word: str, freq: Optional[int] = None, tag: Optional[str] = None):
        """
        Add a single word to the dictionary
        
        Args:
            word: Word
            freq: Word frequency
            tag: POS tag
        """
        jieba.add_word(word, freq=freq, tag=tag)
        logger.debug(f"Word added: {word} (freq={freq}, tag={tag})")


# Global singleton
_tokenizer_instance: Optional[ChineseTokenizer] = None


def get_chinese_tokenizer(use_paddle: bool = False) -> ChineseTokenizer:
    """
    Get Chinese tokenizer singleton
    
    Args:
        use_paddle: Whether to use PaddlePaddle mode
        
    Returns:
        ChineseTokenizer instance
    """
    global _tokenizer_instance
    
    if _tokenizer_instance is None:
        _tokenizer_instance = ChineseTokenizer(use_paddle=use_paddle)
    
    return _tokenizer_instance


def tokenize_for_postgres(text: str, is_tokenized: bool = False) -> str:
    """
    Shortcut function: tokenize for PostgreSQL
    
    Args:
        text: Original text or already tokenized keywords (space-separated)
        is_tokenized: If True, input is already tokenized keywords, only needs cleaning and normalization;
                     If False, requires full tokenization processing
        
    Returns:
        Space-separated tokenization result
    """
    if is_tokenized:
        # Input is already tokenized, only needs simple cleaning
        # Unify to lowercase, remove extra spaces
        tokens = text.split()
        cleaned_tokens = [token.strip().lower() for token in tokens if token.strip()]
        return ' '.join(cleaned_tokens)
    
    # Requires full tokenization
    tokenizer = get_chinese_tokenizer()
    return tokenizer.tokenize_for_postgres(text)


def tokenize_chinese_text(text: str, remove_stopwords: bool = True) -> List[str]:
    """
    Shortcut function: Chinese tokenization
    
    Args:
        text: Original text
        remove_stopwords: Whether to remove stopwords
        
    Returns:
        List of tokenization results
    """
    tokenizer = get_chinese_tokenizer()
    return tokenizer.tokenize(text, remove_stopwords=remove_stopwords)


def prepare_keywords_for_postgres(keywords: List[str]) -> str:
    """
    Prepare keyword list for PostgreSQL query format
    
    This function is specifically for handling already extracted keyword lists (such as output from intent understanding module),
    avoiding duplicate tokenization, only performing necessary cleaning and formatting.
    
    Args:
        keywords: Keyword list (already tokenized)
        
    Returns:
        Space-separated keyword string suitable for PostgreSQL full-text search
        
    Examples:
        >>> keywords = ["artificial intelligence", "career development", "Xiao", "Ming"]
        >>> prepare_keywords_for_postgres(keywords)
        "artificial intelligence career development xiao ming"
    """
    if not keywords:
        return ""
    
    # Clean and normalize keywords
    cleaned_keywords = []
    for keyword in keywords:
        if keyword and isinstance(keyword, str):
            # Remove leading/trailing spaces, convert to lowercase (English)
            cleaned = keyword.strip()
            if cleaned:
                cleaned_keywords.append(cleaned)
    
    # Join with spaces
    return ' '.join(cleaned_keywords)

