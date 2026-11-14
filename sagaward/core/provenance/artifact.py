"""Resolution artifacts: the frozen facts a decision is allowed to consume.

``classify.py`` owns untrusted-string handling and target resolution, so it is
also the one place that may touch the filesystem to identify an artifact. It
freezes the result here and the gate decides over that snapshot — no re-reading
a filesystem that may move under it, and no ``stat`` on a model-chosen path from
inside the decision function.

``path_key`` cannot dedupe hardlinks (``Path.resolve`` follows symlinks, not
inodes), so ``inode_key`` is carried alongside it. Both travel together; neither
is optional when the artifact exists.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from sagaward.core.provenance.ledger import canonical_path, inode_key


class ArtifactRef(BaseModel):
    """A resolved artifact: raw spelling, canonical key, and inode identity."""

    model_config = ConfigDict(frozen=True)

    raw: str
    path_key: str
    inode_key: tuple[int, int] | None

    @classmethod
    def resolve(cls, raw: str) -> ArtifactRef:
        """Resolve ``raw`` once. This is the only call here that touches the filesystem."""
        key = canonical_path(raw)
        return cls(raw=raw, path_key=str(key), inode_key=inode_key(key))

    def is_present(self) -> bool:
        """True when the artifact existed at resolution time."""
        return self.inode_key is not None
