class Cmd:
    MOVE         = 'move'
    ATTACK       = 'attack'
    ATTACK_MOVE  = 'attack_move'
    GATHER       = 'gather'
    BUILD        = 'build'
    STOP         = 'stop'
    PATROL       = 'patrol'


class CmdData:
    """Lightweight command object passed to units."""
    def __init__(self, cmd_type, **kwargs):
        self.type = cmd_type
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        attrs = {k: v for k, v in self.__dict__.items() if k != 'type'}
        return f"CmdData({self.type}, {attrs})"
