"""환경 설정. `.env`에서 읽어오며 OS 비종속 경로를 사용한다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 루트 (이 파일 기준 src/sejong_rag/config.py → 3단계 상위)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API 키 ---
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # --- 모델 ---
    embedding_model: str = Field(default="text-embedding-3-large", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=3072, alias="EMBEDDING_DIM")
    llm_model: str = Field(default="claude-opus-4-8", alias="LLM_MODEL")
    llm_model_cheap: str = Field(default="claude-haiku-4-5", alias="LLM_MODEL_CHEAP")

    # --- 저장 경로 ---
    data_dir: Path = Field(default=BACKEND_ROOT / "data", alias="DATA_DIR")

    # --- 크롤 설정 ---
    crawl_user_agent: str = Field(
        default="SejongRAGBot/0.1 (+contact: example@example.com)",
        alias="CRAWL_USER_AGENT",
    )
    crawl_max_concurrency: int = Field(default=2, alias="CRAWL_MAX_CONCURRENCY")
    crawl_min_delay_sec: float = Field(default=1.0, alias="CRAWL_MIN_DELAY_SEC")
    crawl_max_delay_sec: float = Field(default=3.0, alias="CRAWL_MAX_DELAY_SEC")

    # --- 시간대 ---
    timezone: str = Field(default="Asia/Seoul", alias="TIMEZONE")

    # --- 파생 경로 ---
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "sejong.sqlite"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    def ensure_dirs(self) -> None:
        """필요한 데이터 디렉터리를 생성한다."""
        for p in (self.data_dir, self.raw_dir, self.chroma_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
