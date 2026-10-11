"""Optional asynchronous Windows system feedback; no audio files or persistent worker."""
import winsound


class Sounds:
    def __init__(self, player=None):
        self.player = player or winsound.PlaySound
        self.enabled = False
        self.closed = False
        self._played = False

    def play(self, action):
        if not self.enabled or self.closed or action not in {"enabled", "paused", "resumed"}:
            return
        try:
            self.player("SystemAsterisk" if action != "paused" else "SystemDefault",
                        winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT | winsound.SND_NOSTOP)
            self._played = True
        except (RuntimeError, OSError):
            pass

    def close(self):
        self.closed = True
        if self.enabled or self._played:
            try:
                self.player(None, 0)
            except (RuntimeError, OSError):
                pass
