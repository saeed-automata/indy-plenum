import pip
import importlib
from typing import Dict
import time

from plenum.common.log import getlogger

logger = getlogger()


notifierPluginTriggerEvents = {
    'nodeRequestSpike': 'NodeRequestSuspiciousSpike',
    'clusterThroughputSpike': 'ClusterThroughputSuspiciousSpike',
    # TODO: Implement clusterLatencyTooHigh event triggering
    'clusterLatencyTooHigh': 'ClusterLatencyTooHigh',
    'nodeUpgradeScheduled': 'NodeUpgradeScheduled',
    'nodeUpgradeComplete': 'NodeUpgradeComplete',
    'nodeUpgradeFail': 'NodeUpgradeFail',
    'poolUpgradeCancel': 'PoolUpgradeCancel'
}


class PluginManager:
    prefix = 'sovrinnotifier'
    __instance = None

    def __new__(cls):
        if PluginManager.__instance is None:
            PluginManager.__instance = object.__new__(cls)
        return PluginManager.__instance

    def __init__(self):
        self.plugins = []
        self.topics = notifierPluginTriggerEvents
        self.importPlugins()

    def sendMessageUponNodeUpgradeScheduled(self, message='Node uprgade has been scheduled'):
        return self._sendMessage(self.topics['nodeUpgradeScheduled'], message)

    def sendMessageUponNodeUpgradeComplete(self, message='Node has successfully upgraded.'):
        return self._sendMessage(self.topics['nodeUpgradeComplete'], message)

    def sendMessageUponNodeUpgradeFail(self, message='Node upgrade has failed. Please take action.'):
        return self._sendMessage(self.topics['nodeUpgradeFail'], message)

    def sendMessageUponPoolUpgradeCancel(self, message='Pool upgrade has been cancelled. Please take action.'):
        return self._sendMessage(self.topics['poolUpgradeCancel'], message)

    def sendMessageUponSuspiciousSpike(self, event: str, historicalData: Dict,
                                       newVal: float, config: Dict, nodeName: str):
        assert 'value' in historicalData
        assert 'cnt' in historicalData
        assert 'minCnt' in config
        assert 'coefficient' in config

        coefficient = config['coefficient']
        minCnt = config['minCnt']
        val = historicalData['value']
        cnt = historicalData['cnt']
        historicalData['value'] = \
            val * (cnt / (cnt + 1)) + newVal / (cnt + 1)
        historicalData['cnt'] += 1

        if cnt < minCnt:
            logger.debug('Not enough data to detect a {} spike'.format(event))
            return None

        if (val / coefficient) <= newVal <= (val * coefficient):
            logger.debug('{}: New value {} is within bounds. Average: {}'.format(event, newVal, val))
            return None

        message = '{} suspicious spike has been noticed on node {} at {}. ' \
                  'Usual: {}. New: {}.'\
            .format(event, nodeName, time.time(), val, newVal)
        logger.warning(message)
        return self._sendMessage(event, message)

    def importPlugins(self):
        plugins = self._findPlugins()
        self.plugins = []
        i = 0
        for plugin in plugins:
            try:
                module = importlib.import_module(plugin)
                self.plugins.append(module)
                i += 1
            except Exception as e:
                logger.error('Importing module {} failed due to {}'
                             .format(plugin, e))
        return i, len(plugins)

    def _sendMessage(self, topic, message):
        i = 0
        for plugin in self.plugins:
            try:
                plugin.send_message(topic, message)
                i += 1
            except Exception as e:
                logger.error('Sending message failed for plugin {} due to {}'
                             .format(plugin.__name__, e))
        return i, len(self.plugins)

    def _findPlugins(self):
        return [pkg.key
                for pkg in pip.utils.get_installed_distributions()
                if pkg.key.startswith(PluginManager.prefix)]