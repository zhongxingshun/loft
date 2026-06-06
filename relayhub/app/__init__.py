"""RelayHub —— ISP IP 中转开通服务。

模块依赖方向: api / scripts -> provisioning -> {marzban, guard, parsing, models, config}
provisioning 是唯一编排者, CLI 与 Web 共用, 保证安全护栏不可旁路。
"""

__version__ = "0.1.0"
