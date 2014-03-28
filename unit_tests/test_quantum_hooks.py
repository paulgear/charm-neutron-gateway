from mock import MagicMock, patch, call
import charmhelpers.core.hookenv as hookenv
hookenv.config = MagicMock()
import quantum_utils as utils
_register_configs = utils.register_configs
_restart_map = utils.restart_map
utils.register_configs = MagicMock()
utils.restart_map = MagicMock()
import quantum_hooks as hooks
utils.register_configs = _register_configs
utils.restart_map = _restart_map

from test_utils import CharmTestCase


TO_PATCH = [
    'config',
    'configure_installation_source',
    'valid_plugin',
    'apt_update',
    'apt_install',
    'filter_installed_packages',
    'get_early_packages',
    'get_packages',
    'log',
    'do_openstack_upgrade',
    'openstack_upgrade_available',
    'CONFIGS',
    'configure_ovs',
    'relation_set',
    'relation_ids',
    'unit_get',
    'relation_get',
    'install_ca_cert',
    'eligible_leader',
    'reassign_agent_resources',
    'get_common_package',
    'execd_preinstall',
    'lsb_release',
    'stop_services',
    'b64decode',
    'is_relation_made'
]


def passthrough(value):
    return value


class TestQuantumHooks(CharmTestCase):

    def setUp(self):
        super(TestQuantumHooks, self).setUp(hooks, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.test_config.set('openstack-origin', 'cloud:precise-havana')
        self.test_config.set('plugin', 'ovs')
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'precise'}
        self.b64decode.side_effect = passthrough
        hookenv.config.side_effect = self.test_config.get

    def _call_hook(self, hookname):
        hooks.hooks.execute([
            'hooks/{}'.format(hookname)])

    def test_install_hook(self):
        self.valid_plugin.return_value = True
        _pkgs = ['foo', 'bar']
        self.filter_installed_packages.return_value = _pkgs
        self._call_hook('install')
        self.configure_installation_source.assert_called_with(
            'cloud:precise-havana'
        )
        self.apt_update.assert_called_with(fatal=True)
        self.apt_install.assert_has_calls([
            call(_pkgs, fatal=True),
            call(_pkgs, fatal=True),
        ])
        self.get_early_packages.assert_called()
        self.get_packages.assert_called()
        self.execd_preinstall.assert_called()

    def test_install_hook_precise_nocloudarchive(self):
        self.test_config.set('openstack-origin', 'distro')
        self._call_hook('install')
        self.configure_installation_source.assert_called_with(
            'cloud:precise-folsom'
        )

    @patch('sys.exit')
    def test_install_hook_invalid_plugin(self, _exit):
        self.valid_plugin.return_value = False
        self._call_hook('install')
        self.log.assert_called()
        _exit.assert_called_with(1)

    def test_config_changed_upgrade(self):
        self.openstack_upgrade_available.return_value = True
        self.valid_plugin.return_value = True
        self._call_hook('config-changed')
        self.do_openstack_upgrade.assert_called_with(self.CONFIGS)
        self.CONFIGS.write_all.assert_called()
        self.configure_ovs.assert_called()

    @patch('sys.exit')
    def test_config_changed_invalid_plugin(self, _exit):
        self.valid_plugin.return_value = False
        self._call_hook('config-changed')
        self.log.assert_called()
        _exit.assert_called_with(1)

    def test_upgrade_charm(self):
        _install = self.patch('install')
        _config_changed = self.patch('config_changed')
        self._call_hook('upgrade-charm')
        self.assertTrue(_install.called)
        self.assertTrue(_config_changed.called)

    def test_db_joined(self):
        self.is_relation_made.return_value = False
        self.unit_get.return_value = 'myhostname'
        self._call_hook('shared-db-relation-joined')
        self.relation_set.assert_called_with(
            username='nova',
            database='nova',
            hostname='myhostname',
            relation_id=None
        )

    def test_db_joined_with_postgresql(self):
        self.is_relation_made.return_value = True

        with self.assertRaises(Exception) as context:
            hooks.db_joined()
        self.assertEqual(context.exception.message,
            'Attempting to associate a mysql database when there '
            'is already associated a postgresql one')

    def test_postgresql_db_joined(self):
        self.unit_get.return_value = 'myhostname'
        self.is_relation_made.return_value = False
        self._call_hook('pgsql-db-relation-joined')
        self.relation_set.assert_called_with(
            database='nova'
        )

    def test_postgresql_joined_with_db(self):
        self.is_relation_made.return_value = True

        with self.assertRaises(Exception) as context:
            hooks.pgsql_db_joined()
        self.assertEqual(context.exception.message,
            'Attempting to associate a postgresql database when there '
            'is already associated a mysql one')

    def test_amqp_joined(self):
        self._call_hook('amqp-relation-joined')
        self.relation_set.assert_called_with(
            username='neutron',
            vhost='openstack',
            relation_id=None
        )

    def test_amqp_changed(self):
        self._call_hook('amqp-relation-changed')
        self.CONFIGS.write_all.assert_called()

    def test_shared_db_changed(self):
        self._call_hook('shared-db-relation-changed')
        self.CONFIGS.write_all.assert_called()

    def test_pgsql_db_changed(self):
        self._call_hook('pgsql-db-relation-changed')
        self.CONFIGS.write_all.assert_called()

    def test_nm_changed(self):
        self.relation_get.return_value = "cert"
        self._call_hook('quantum-network-service-relation-changed')
        self.CONFIGS.write_all.assert_called()
        self.install_ca_cert.assert_called_with('cert')

    def test_cluster_departed_nvp(self):
        self.test_config.set('plugin', 'nvp')
        self._call_hook('cluster-relation-departed')
        self.log.assert_called()
        self.eligible_leader.assert_not_called()
        self.reassign_agent_resources.assert_not_called()

    def test_cluster_departed_ovs_not_leader(self):
        self.eligible_leader.return_value = False
        self._call_hook('cluster-relation-departed')
        self.reassign_agent_resources.assert_not_called()

    def test_cluster_departed_ovs_leader(self):
        self.eligible_leader.return_value = True
        self._call_hook('cluster-relation-departed')
        self.reassign_agent_resources.assert_called()

    def test_stop(self):
        self._call_hook('stop')
        self.stop_services.assert_called
