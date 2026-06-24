import pandas as pd
from typing import BinaryIO
import io
import zipfile

class DatasetParser:
    @staticmethod
    def parse_csv(file_bytes: bytes, delimiter: str = ",") -> pd.DataFrame:
        """Parses CSV bytes into a pandas DataFrame using chunking/streaming configurations if needed."""
        # Use simple io.BytesIO stream
        return pd.read_csv(io.BytesIO(file_bytes), sep=delimiter)

    @staticmethod
    def parse_parquet(file_bytes: bytes) -> pd.DataFrame:
        """Parses Parquet bytes into a pandas DataFrame."""
        return pd.read_parquet(io.BytesIO(file_bytes))

    @staticmethod
    def parse_xlsx(file_bytes: bytes) -> pd.DataFrame:
        """Parses the first sheet of Excel bytes into a pandas DataFrame."""
        return pd.read_excel(io.BytesIO(file_bytes))

    @staticmethod
    def parse_json(file_bytes: bytes) -> pd.DataFrame:
        """Parses JSON bytes into a pandas DataFrame."""
        return pd.read_json(io.BytesIO(file_bytes))
