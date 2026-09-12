# Superficie pública del provider Blob; no expone ETag ni tipos Azure.
from atlanticus.web.source.blob.store import BlobSourceSettings, BlobSourceStore

__all__ = ['BlobSourceSettings', 'BlobSourceStore']
