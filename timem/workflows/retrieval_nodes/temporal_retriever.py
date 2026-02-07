"""
Temporal retrieval node

Responsible for memory retrieval based on time ranges,
especially suitable for queries containing time entities
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import re

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator, RetrievalStrategy
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class TemporalRetriever:
    """Temporal retrieval node"""  # Reference memory_generation node design
    
    def __init__(self, 
                 storage_manager=None,
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize temporal retrieval node
        
        Args:
            storage_manager: Storage manager
            state_validator: State validator
        """
        self.storage_manager = storage_manager
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run temporal retrieval node
        
        Args:
            state: Current state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert dictionary to RetrievalState object
            retrieval_state = RetrievalState(**state)
            
            # Check if temporal retrieval strategy is selected
            strategy_values = [s.value if hasattr(s, 'value') else str(s) for s in retrieval_state.selected_strategies]
            if RetrievalStrategy.TEMPORAL.value not in strategy_values and RetrievalStrategy.TEMPORAL not in retrieval_state.selected_strategies:
                self.logger.info("Skip temporal retrieval: strategy not selected")
                return retrieval_state.to_dict()
            
            # Check if time entities exist
            if not retrieval_state.time_entities:
                self.logger.info("Skip temporal retrieval: no time entities")
                return retrieval_state.to_dict()
            
            self.logger.info(f"Start temporal retrieval, time entity count: {len(retrieval_state.time_entities)}")
            
            # Initialize storage manager
            if not self.storage_manager:
                self.storage_manager = await get_memory_storage_manager_async()
            
            # Perform temporal retrieval
            results = await self._perform_temporal_search(retrieval_state)
            
            # Process and mark results
            processed_results = await self._process_results(results, retrieval_state)
            
            retrieval_state.temporal_results = processed_results
            retrieval_state.total_memories_searched += len(processed_results)
            
            self.logger.info(f"📅 Temporal retrieval complete: {len(processed_results)} results")
            
            # Convert back to dictionary format and return
            return retrieval_state.to_dict()
            
        except Exception as e:
            self.logger.error(f"❌ Temporal retrieval failed: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Temporal retrieval failed: {str(e)}"]
            state["success"] = False
            return state
    
    async def _perform_temporal_search(self, state: RetrievalState) -> List[Any]:
        """Perform time-based retrieval"""
        all_results = []
        
        try:
            # Retrieve for each time entity
            for time_entity in state.time_entities:
                time_window = self._calculate_time_window(time_entity, state)
                
                query = {
                    "user_id": state.user_id,
                    "expert_id": state.expert_id
                }
                
                options = {
                    "start_time": time_window["start"],
                    "end_time": time_window["end"],
                    "limit": state.retrieval_params.get("max_results_per_strategy", 20),
                    "sort_by": "timestamp",  # Sort by timestamp
                    "sort_order": "desc"
                }
                
                self.logger.info(f"Time window retrieval: {time_window['start']} to {time_window['end']}")
                
                # Retrieve from SQL storage (temporal retrieval is primarily SQL-based)
                temp_results = await self.storage_manager.sql_adapter.search_memories(query, options)
                
                # Add temporal relevance score for each result
                for result in temp_results:
                    if hasattr(result, 'timestamp'):
                        result.temporal_relevance = self._calculate_temporal_relevance(
                            result.timestamp, time_entity, time_window
                        )
                
                all_results.extend(temp_results)
                
                self.logger.info(f"Time entity '{time_entity['text']}' retrieved {len(temp_results)} results")
            
            return all_results
            
        except Exception as e:
            self.logger.error(f"Temporal retrieval execution failed: {str(e)}")
            raise
    
    def _calculate_time_window(self, time_entity: Dict[str, Any], state: RetrievalState) -> Dict[str, datetime]:
        """Calculate time window"""
        try:
            time_text = time_entity["text"]
            time_type = time_entity["type"]
            
            if time_type == "year":
                # Year: full year range
                year = int(time_text)
                start = datetime(year, 1, 1)
                end = datetime(year, 12, 31, 23, 59, 59)
                
            elif time_type in ["date", "full_date", "chinese_date"]:
                # Specific date: day range
                if time_type == "chinese_date":
                    # Parse Chinese date format: YYYY年MM月DD日 (year-month-day)
                    match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', time_text)
                    if match:
                        year, month, day = map(int, match.groups())
                        start = datetime(year, month, day)
                        end = datetime(year, month, day, 23, 59, 59)
                    else:
                        raise ValueError(f"Cannot parse Chinese date: {time_text}")
                else:
                    # Other date format parsing can be extended here
                    # Currently use default window
                    start = datetime.now() - timedelta(days=30)
                    end = datetime.now()
                    
            elif time_type in ["relative", "relative_chinese"]:
                # Relative time
                now = datetime.now()
                if "yesterday" in time_text or "yesterday" in time_text:
                    start = now - timedelta(days=1)
                    end = now - timedelta(hours=1)
                elif "today" in time_text or "today" in time_text:
                    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    end = now
                elif "last week" in time_text or "last week" in time_text:
                    start = now - timedelta(weeks=1)
                    end = now - timedelta(days=1)
                elif "last month" in time_text or "last month" in time_text:
                    start = now - timedelta(days=30)
                    end = now - timedelta(days=1)
                else:
                    # Default to last week
                    start = now - timedelta(weeks=1)
                    end = now
                    
            elif time_type in ["ago", "ago_chinese"]:
                # XX time ago
                now = datetime.now()
                # Extract number and unit
                if time_type == "ago":
                    match = re.search(r'(\d+)\s+(days?|weeks?|months?|years?)', time_text)
                    if match:
                        number, unit = match.groups()
                        number = int(number)
                        if "day" in unit:
                            start = now - timedelta(days=number+1)
                            end = now - timedelta(days=number-1)
                        elif "week" in unit:
                            start = now - timedelta(weeks=number+1)
                            end = now - timedelta(weeks=number-1)
                        elif "month" in unit:
                            start = now - timedelta(days=(number+1)*30)
                            end = now - timedelta(days=(number-1)*30)
                        elif "year" in unit:
                            start = now - timedelta(days=(number+1)*365)
                            end = now - timedelta(days=(number-1)*365)
                        else:
                            start = now - timedelta(days=30)
                            end = now
                    else:
                        start = now - timedelta(days=30)
                        end = now
                else:
                    # Parse Chinese time ago
                    start = now - timedelta(days=30)
                    end = now
                    
            else:
                # Default time window
                window_days = state.retrieval_params.get("temporal_window_days", 30)
                now = datetime.now()
                start = now - timedelta(days=window_days)
                end = now
            
            return {"start": start, "end": end}
            
        except Exception as e:
            self.logger.warning(f"Time window calculation failed: {e}, using default window")
            # Default time window
            window_days = state.retrieval_params.get("temporal_window_days", 30)
            now = datetime.now()
            return {
                "start": now - timedelta(days=window_days),
                "end": now
            }
    
    def _calculate_temporal_relevance(self, result_time: datetime, time_entity: Dict[str, Any], 
                                    time_window: Dict[str, datetime]) -> float:
        """Calculate temporal relevance score"""
        try:
            if not result_time:
                return 0.5
            
            window_start = time_window["start"]
            window_end = time_window["end"]
            
            # Check if within time window
            if window_start <= result_time <= window_end:
                # Within window, calculate relative position score
                window_duration = (window_end - window_start).total_seconds()
                if window_duration > 0:
                    # Closer to window center, higher score
                    window_center = window_start + (window_end - window_start) / 2
                    distance_from_center = abs((result_time - window_center).total_seconds())
                    relevance = 1.0 - (distance_from_center / (window_duration / 2))
                    return max(0.7, min(1.0, relevance))  # Ensure minimum score of 0.7 within time window
                else:
                    return 0.9  # Time point match
            else:
                # Outside window, calculate distance penalty
                if result_time < window_start:
                    distance = (window_start - result_time).total_seconds()
                else:
                    distance = (result_time - window_end).total_seconds()
                
                # Farther distance, lower score
                days_distance = distance / (24 * 3600)
                if days_distance <= 1:
                    return 0.6
                elif days_distance <= 7:
                    return 0.4
                elif days_distance <= 30:
                    return 0.2
                else:
                    return 0.1
                    
        except Exception as e:
            self.logger.warning(f"Temporal relevance calculation failed: {e}")
            return 0.5
    
    async def _process_results(self, results: List[Any], state: RetrievalState) -> List[Dict[str, Any]]:
        """Process retrieval results and convert to unified format"""
        processed_results = []
        
        # Deduplicate (based on ID)
        seen_ids = set()
        
        for i, result in enumerate(results):
            try:
                # Get result ID
                result_id = getattr(result, 'id', f"temporal_{i}")
                if result_id in seen_ids:
                    continue
                seen_ids.add(result_id)
                
                # Convert to dictionary format
                if hasattr(result, 'to_dict'):
                    result_dict = result.to_dict()
                elif isinstance(result, dict):
                    result_dict = result.copy()
                else:
                    result_dict = {
                        "id": result_id,
                        "content": getattr(result, 'content', str(result)),
                        "level": getattr(result, 'level', 'Unknown'),
                        "user_id": getattr(result, 'user_id', state.user_id),
                        "expert_id": getattr(result, 'expert_id', state.expert_id),
                        "timestamp": getattr(result, 'timestamp', None)
                    }
                
                # Add retrieval source and score information
                result_dict["retrieval_source"] = "temporal"
                
                # Use temporal relevance as retrieval score
                temporal_relevance = getattr(result, 'temporal_relevance', 0.8)
                result_dict["retrieval_score"] = temporal_relevance
                
                # Apply temporal weight
                temporal_weight = state.retrieval_params.get("temporal_weight", 0.8)
                result_dict["weighted_score"] = result_dict["retrieval_score"] * temporal_weight
                
                processed_results.append(result_dict)
                
            except Exception as e:
                self.logger.warning(f"Processing temporal retrieval result[{i}] failed: {str(e)}")
                continue
        
        # Sort by temporal relevance
        processed_results.sort(key=lambda x: x.get("retrieval_score", 0.0), reverse=True)
        
        self.logger.info(f"Temporal retrieval result processing complete: {len(processed_results)} valid results")
        
        return processed_results
