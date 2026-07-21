import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_service.dart';
import 'connection_screen.dart';

class SettingsScreen extends StatefulWidget {
  final String baseUrl;

  const SettingsScreen({super.key, required this.baseUrl});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final ApiService api;
  late final Future<String> hlsUrlFuture;

  bool checkingConnection = false;
  String? connectionMessage;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    hlsUrlFuture = api.getConfiguredHlsUrl();
  }

  Future<void> _testConnection() async {
    setState(() {
      checkingConnection = true;
      connectionMessage = null;
    });

    final ok = await api.testConnection();

    if (!mounted) return;

    setState(() {
      checkingConnection = false;
      connectionMessage = ok
          ? 'Conexión correcta con el backend'
          : 'No se pudo conectar con el backend';
    });
  }

  Future<void> _changeServer() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('backend_url');

    if (!mounted) return;

    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const ConnectionScreen()),
      (route) => false,
    );
  }

  Widget _buildInfoCard({
    required IconData icon,
    required String title,
    required String value,
  }) {
    return Card(
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: SelectableText(value),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(centerTitle: true, title: const Text('Configuración')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Conexión', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),

          _buildInfoCard(
            icon: Icons.dns,
            title: 'Backend FastAPI',
            value: widget.baseUrl,
          ),

          FutureBuilder<String>(
            future: hlsUrlFuture,
            builder: (context, snapshot) => _buildInfoCard(
              icon: Icons.graphic_eq,
              title: 'URL HLS',
              value: snapshot.data ?? api.getHlsUrl(),
            ),
          ),

          const SizedBox(height: 16),

          ElevatedButton.icon(
            onPressed: checkingConnection ? null : _testConnection,
            icon: checkingConnection
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.wifi_tethering),
            label: const Text('Probar conexión'),
          ),

          if (connectionMessage != null) ...[
            const SizedBox(height: 12),
            Text(connectionMessage!),
          ],

          const SizedBox(height: 24),

          Text('Servidor', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),

          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Usa la IP LAN o Tailscale del servidor. No uses 127.0.0.1 en móvil real, porque apunta al propio móvil.',
                  ),
                  const SizedBox(height: 16),
                  OutlinedButton.icon(
                    onPressed: _changeServer,
                    icon: const Icon(Icons.swap_horiz),
                    label: const Text('Cambiar servidor'),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 24),

          Text('Aplicación', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),

          const Card(
            child: ListTile(
              leading: Icon(Icons.info_outline),
              title: Text('BirdMonitor App'),
              subtitle: Text(
                'Cliente móvil para consulta de detecciones, métricas ecológicas y control de escucha en directo.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
