import logging
import time
from typing import Any, Dict, Optional, Union
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance

from timem.utils.logging import get_logger

logger = get_logger(__name__)

def _create_new_collection(client: QdrantClient, collection_name: str, vector_size: int, distance: models.Distance):
    """
    Internal helper function: Create a new Qdrant collection and set payload indexes for key fields.
    """
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=distance
        )
    )
    logger.info(f"✅ Collection '{collection_name}' created successfully.")
    
    # Create integer index for created_at_ts field
    client.create_payload_index(
        collection_name=collection_name,
        field_name="created_at_ts",
        field_schema=models.PayloadSchemaType.INTEGER,
        wait=True
    )
    logger.info(f"✅ Created integer index for 'created_at_ts' field in collection '{collection_name}'.")

def ensure_collection_with_correct_dim(
    client: QdrantClient, 
    collection_name: str, 
    expected_vector_size: int, 
    distance_metric: str = "Cosine"
) -> bool:
    """
    Ensure Qdrant collection exists and has correct vector dimension. Create it if it doesn't exist.
    """
    try:
        collection_info = client.get_collection(collection_name=collection_name)
        
        existing_vector_size = _extract_vector_size_from_collection_info(collection_info)

        if existing_vector_size is None:
            raise ValueError(f"Unable to extract vector dimension from collection '{collection_name}' info.")

        if existing_vector_size == expected_vector_size:
            logger.info(f"✅ Collection '{collection_name}' exists with correct dimension ({existing_vector_size}).")
            return True
        else:
            logger.warning(
                f"⚠️ Collection '{collection_name}' exists but dimension mismatch "
                f"(existing: {existing_vector_size}, required: {expected_vector_size}). "
                f"Recreating collection..."
            )
            client.delete_collection(collection_name=collection_name)
            logger.info(f"🗑️ Old collection '{collection_name}' deleted.")
            
            distance = Distance.COSINE if distance_metric.upper() == 'COSINE' else Distance.DOT
            _create_new_collection(client, collection_name, expected_vector_size, distance)
            return True

    except Exception as e:
        error_str = str(e).lower()
        # Check if it's a "not found" type error
        if "not found" in error_str or "404" in error_str or "does not exist" in error_str:
            logger.info(f"🚀 Collection '{collection_name}' does not exist, creating (dimension: {expected_vector_size})...")
            distance = Distance.COSINE if distance_metric.upper() == 'COSINE' else Distance.DOT
            try:
                _create_new_collection(client, collection_name, expected_vector_size, distance)
                return True
            except Exception as create_exc:
                logger.error(f"❌ Failed to create collection '{collection_name}': {create_exc}")
                return False
        else:
            logger.error(f"❌ Failed to check collection '{collection_name}': {e}")
            return False


def _extract_vector_size_from_collection_info(collection_info: Any) -> Optional[int]:
    """
    Extract vector dimension from collection info, supporting multiple possible structure formats
    
    Args:
        collection_info: Collection info object obtained from Qdrant
        
    Returns:
        Vector dimension, returns None if unable to determine
    """
    # Handle qdrant_client > 1.7.0 uniformly
    if hasattr(collection_info, 'vectors_config') and collection_info.vectors_config:
        # Check if it's dict form
        if isinstance(collection_info.vectors_config, dict):
            # Compatible with {'': VectorParams(...)} form
            if '' in collection_info.vectors_config and hasattr(collection_info.vectors_config[''], 'params'):
                 return collection_info.vectors_config[''].params.size
            # Compatible with {'default': VectorParams(...)}
            if 'default' in collection_info.vectors_config and hasattr(collection_info.vectors_config['default'], 'params'):
                 return collection_info.vectors_config['default'].params.size
        # Check if it's object form
        elif hasattr(collection_info.vectors_config, 'params'):
            return collection_info.vectors_config.params.size
            
    # Handle qdrant_client < 1.7.0
    if hasattr(collection_info, 'config') and hasattr(collection_info.config, 'params') and hasattr(collection_info.config.params, 'vectors') and hasattr(collection_info.config.params.vectors, 'size'):
        return collection_info.config.params.vectors.size
    
    # If vector dimension not found, return None
    return None
