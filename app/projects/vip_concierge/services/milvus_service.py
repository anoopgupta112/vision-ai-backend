import logging
import math
import os
from typing import Any, Dict, List, Optional

try:
    import numpy as np
except ImportError:
    np = None

from app.core.config import Config

logger = logging.getLogger(__name__)

FACE_COLLECTION_NAME = "vip_face_embeddings"
PREFERENCE_COLLECTION_NAME = "customer_preference_embeddings"
FACE_VECTOR_DIM = 512
GEMINI_VECTOR_DIM = 768


class MilvusService:
    def __init__(self):
        self.host = getattr(Config, "MILVUS_HOST", "localhost")
        self.port = getattr(Config, "MILVUS_PORT", 19530)
        self.connected = False
        self._face_collection = None
        self._pref_collection = None
        # In-memory fallback if Milvus is temporarily unreachable (for unit tests / dev)
        self._fallback_faces: List[Dict[str, Any]] = []

    def connect(self) -> bool:
        if self.connected:
            return True
        try:
            from pymilvus import connections
            connections.connect(
                alias="default",
                host=self.host,
                port=str(self.port),
                timeout=3.0,
            )
            self.connected = True
            self._ensure_collections()
            logger.info("Successfully connected to Milvus at %s:%s", self.host, self.port)
            return True
        except Exception as exc:
            logger.warning(
                "Could not connect to Milvus at %s:%s (%s). Using fallback vector engine.",
                self.host,
                self.port,
                exc,
            )
            self.connected = False
            return False

    def _ensure_collections(self):
        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

            # 1. Face Embeddings Collection (512-d from InsightFace AntelopeV2)
            if not utility.has_collection(FACE_COLLECTION_NAME):
                fields = [
                    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                    FieldSchema(name="customer_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="shop_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=FACE_VECTOR_DIM),
                ]
                schema = CollectionSchema(fields=fields, description="VIP Face Biometric Vectors")
                collection = Collection(name=FACE_COLLECTION_NAME, schema=schema)
                index_params = {
                    "metric_type": "COSINE",
                    "index_type": "HNSW",
                    "params": {"M": 8, "efConstruction": 64},
                }
                collection.create_index(field_name="embedding", index_params=index_params)
                logger.info("Created Milvus collection: %s", FACE_COLLECTION_NAME)
            
            self._face_collection = Collection(name=FACE_COLLECTION_NAME)
            self._face_collection.load()

            # 2. Customer Preference Collection (768-d from Gemini Embeddings)
            if not utility.has_collection(PREFERENCE_COLLECTION_NAME):
                fields = [
                    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                    FieldSchema(name="customer_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="shop_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=GEMINI_VECTOR_DIM),
                ]
                schema = CollectionSchema(fields=fields, description="Customer Semantic Taste Vectors")
                pref_col = Collection(name=PREFERENCE_COLLECTION_NAME, schema=schema)
                pref_params = {
                    "metric_type": "COSINE",
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 128},
                }
                pref_col.create_index(field_name="embedding", index_params=pref_params)
                logger.info("Created Milvus collection: %s", PREFERENCE_COLLECTION_NAME)

            self._pref_collection = Collection(name=PREFERENCE_COLLECTION_NAME)
            self._pref_collection.load()

        except Exception as exc:
            logger.error("Error setting up Milvus collections: %s", exc)

    def _normalize(self, vec: List[float]) -> List[float]:
        if np is not None:
            norm = float(np.linalg.norm(vec))
            return (np.array(vec) / (norm + 1e-9)).tolist()
        norm = math.sqrt(sum(x * x for x in vec)) + 1e-9
        return [x / norm for x in vec]

    def _cosine_sim(self, v1: List[float], v2: List[float]) -> float:
        if np is not None:
            return float(np.dot(v1, v2))
        return sum(a * b for a, b in zip(v1, v2))

    def insert_face_embedding(self, customer_id: str, shop_id: str, embedding: List[float]) -> bool:
        """Stores a 512-d normalized face vector for a customer."""
        norm_vec = self._normalize(embedding)

        if self.connect() and self._face_collection:
            try:
                self._face_collection.insert([
                    [customer_id],
                    [shop_id or "default"],
                    [norm_vec],
                ])
                self._face_collection.flush()
                return True
            except Exception as exc:
                logger.error("Milvus insert_face_embedding failed: %s", exc)

        # Fallback local store
        existing_idx = next((i for i, f in enumerate(self._fallback_faces) if f.get("customer_id") == customer_id), -1)
        item = {
            "customer_id": customer_id,
            "shop_id": shop_id or "default",
            "embedding": norm_vec,
        }
        if existing_idx >= 0:
            self._fallback_faces[existing_idx] = item
        else:
            self._fallback_faces.append(item)
        return True

    def hydrate_from_db(self):
        """Pulls all customer face embeddings stored in MongoDB into memory/index."""
        try:
            from app.core.database import get_collection
            customers = list(get_collection("vip_customers").find({"face_embedding": {"$exists": True, "$ne": None}}))
            loaded = 0
            for doc in customers:
                cid = str(doc["_id"])
                shop_id = doc.get("shop_id", "default")
                emb = doc.get("face_embedding")
                if emb and len(emb) == FACE_VECTOR_DIM:
                    existing_idx = next((i for i, f in enumerate(self._fallback_faces) if f.get("customer_id") == cid), -1)
                    item = {
                        "customer_id": cid,
                        "shop_id": shop_id,
                        "embedding": self._normalize(emb),
                    }
                    if existing_idx >= 0:
                        self._fallback_faces[existing_idx] = item
                    else:
                        self._fallback_faces.append(item)
                    loaded += 1
            if loaded > 0:
                logger.info("Hydrated %d VIP face embeddings from MongoDB into vector search (total: %d)", loaded, len(self._fallback_faces))
        except Exception as exc:
            logger.warning("Could not hydrate face vectors from database: %s", exc)

    def search_face(
        self,
        query_embedding: List[float],
        shop_id: Optional[str] = None,
        threshold: float = 0.65,
        top_k: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """Searches for a matching face vector with cosine similarity >= threshold."""
        norm_vec = self._normalize(query_embedding)

        if self.connect() and self._face_collection:
            try:
                search_params = {"metric_type": "COSINE", "params": {"ef": 64}}
                expr = f'shop_id == "{shop_id}"' if shop_id else None
                results = self._face_collection.search(
                    data=[norm_vec],
                    anns_field="embedding",
                    param=search_params,
                    limit=top_k,
                    expr=expr,
                    output_fields=["customer_id", "shop_id"],
                )

                if results and len(results[0]) > 0:
                    top_hit = results[0][0]
                    confidence = float(top_hit.distance)  # Cosine distance in Milvus represents similarity
                    cid = top_hit.entity.get("customer_id")
                    if confidence >= threshold:
                        return {
                            "customer_id": cid,
                            "confidence": round(confidence, 4),
                            "shop_id": top_hit.entity.get("shop_id"),
                            "matched": True,
                        }
                    return {
                        "matched": False,
                        "best_score": round(confidence, 4),
                        "best_candidate_id": cid,
                    }
                return {"matched": False, "best_score": 0.0}
            except Exception as exc:
                logger.error("Milvus search_face failed: %s, falling back to local search", exc)

        # Fallback in-memory search
        if not self.connected and len(self._fallback_faces) == 0:
            self.hydrate_from_db()

        best_match = None
        best_score = -1.0

        for item in self._fallback_faces:
            if shop_id and item.get("shop_id") and item.get("shop_id") not in [shop_id, "default"]:
                continue
            sim = self._cosine_sim(norm_vec, item["embedding"])
            if sim > best_score:
                best_score = sim
                best_match = item

        if best_match and best_score >= threshold:
            return {
                "customer_id": best_match["customer_id"],
                "confidence": round(best_score, 4),
                "shop_id": best_match.get("shop_id", "default"),
                "matched": True,
            }
        return {
            "matched": False,
            "best_score": round(best_score, 4) if best_score > -1 else 0.0,
            "best_candidate_id": best_match["customer_id"] if best_match else None,
        }

    def delete_customer_faces(self, customer_id: str):
        """Removes embeddings for a given customer."""
        if self.connect() and self._face_collection:
            try:
                expr = f'customer_id == "{customer_id}"'
                self._face_collection.delete(expr)
            except Exception as exc:
                logger.warning("Milvus delete_customer_faces failed: %s", exc)

        self._fallback_faces = [f for f in self._fallback_faces if f.get("customer_id") != customer_id]


milvus_client = MilvusService()
