def classFactory(iface):
    from .macrophyte_plugin import MacrophyteDataPlugin
    return MacrophyteDataPlugin(iface)