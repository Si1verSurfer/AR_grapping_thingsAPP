import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const MaterialApp(
    home: ARDuckHandApp(),
    debugShowCheckedModeBanner: false,
  ));
}

class ARDuckHandApp extends StatefulWidget {
  const ARDuckHandApp({super.key});
  @override State<ARDuckHandApp> createState() => _ARDuckHandAppState();
}

class _ARDuckHandAppState extends State<ARDuckHandApp> {
  // === STATE ===
  String serverUrl = 'http://192.168.1.100:5000'; // UPDATE WITH YOUR PC IP
  final TextEditingController _urlController = TextEditingController();

  bool isConnected = false;
  bool isStreaming = false;
  bool debugMode = true;
  Uint8List? currentFrame;
  double fps = 0;

  List<Map<String, dynamic>> objects = [];
  List<String> debugLogs = [];
  int? grabbedDuckId;

  double scale = 0.5;
  double rotation = 0.0;

  final http.Client client = http.Client();

  @override
  void initState() {
    super.initState();
    _urlController.text = serverUrl;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _testConnection();
    });
  }

  @override
  void dispose() {
    client.close();
    super.dispose();
  }

  void _log(String message) {
    if (debugMode) {
      final timestamp = DateTime.now().toString().split(' ')[1].substring(0, 8);
      debugLogs.insert(0, "[$timestamp] $message");
      if (debugLogs.length > 20) debugLogs.removeLast();
      print(message);
      setState(() {});
    }
  }

  Future<void> _testConnection() async {
    _log("Testing connection...");
    setState(() => isConnected = false);

    try {
      final response = await client
          .get(Uri.parse('$serverUrl/'))
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _log("✅ Connected!");
        _log("Mode: ${data['mode']}");
        _log("Hand Detection: ${data['hand_detection']}");
        setState(() => isConnected = true);
      } else {
        _log("❌ Server error: ${response.statusCode}");
      }
    } catch (e) {
      _log("❌ Connection failed: ${e.toString()}");
    }
  }

  Future<void> _startStream() async {
    if (!isConnected) return;

    _log("Starting AR stream...");
    setState(() => isStreaming = true);

    // Start frame polling
    _pollFrames();
  }

  Future<void> _stopStream() async {
    _log("Stopping stream...");
    setState(() {
      isStreaming = false;
      currentFrame = null;
    });
  }

  void _pollFrames() {
    Future.doWhile(() async {
      if (!isStreaming || !isConnected) return false;

      try {
        final response = await client
            .get(Uri.parse('$serverUrl/camera/frame'))
            .timeout(const Duration(seconds: 5));

        if (response.statusCode == 200) {
          final data = jsonDecode(response.body);

          if (data['frame'] != null) {
            final frameData = base64Decode(data['frame']);

            setState(() {
              currentFrame = frameData;
              if (data['objects'] is List) {
                objects = List<Map<String, dynamic>>.from(data['objects']);
              }
              grabbedDuckId = data['grabbed_duck_id'];
              if (data['fps'] != null) {
                fps = (data['fps'] as num).toDouble();
              }
            });
          }
        }
      } catch (e) {
        _log("Frame error: $e");
      }

      await Future.delayed(const Duration(milliseconds: 100));
      return isStreaming && isConnected;
    });
  }

  Future<void> _placeDuck(Offset position, Size screenSize) async {
    final x = position.dx / screenSize.width;
    final y = position.dy / screenSize.height;

    _log("Placing duck at (${x.toStringAsFixed(2)}, ${y.toStringAsFixed(2)})");

    try {
      final response = await client.post(
        Uri.parse('$serverUrl/ar/tap'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'x': x,
          'y': y,
          'scale': scale,
          'rotation': {'x': 0, 'y': rotation, 'z': 0},
        }),
      );

      if (response.statusCode == 200) {
        final responseData = jsonDecode(response.body);
        _log("✅ ${responseData['message']}");
      }
    } catch (e) {
      _log("Place error: $e");
    }
  }

  Future<void> _deleteDuck(String duckId) async {
    _log("Deleting duck $duckId");

    try {
      final response = await client.delete(Uri.parse('$serverUrl/object/$duckId'));

      if (response.statusCode == 200) {
        final responseData = jsonDecode(response.body);
        if (responseData['success'] == true) {
          setState(() {
            objects.removeWhere((obj) => obj['id'].toString() == duckId);
          });
          _log("✅ Duck deleted");
        }
      }
    } catch (e) {
      _log("Delete error: $e");
    }
  }

  Future<void> _clearAll() async {
    _log("Clearing all ducks");

    try {
      final response = await client.post(Uri.parse('$serverUrl/objects/clear'));

      if (response.statusCode == 200) {
        final responseData = jsonDecode(response.body);
        if (responseData['success'] == true) {
          setState(() {
            objects.clear();
          });
          _log("✅ Cleared ${responseData['count']} ducks");
        }
      }
    } catch (e) {
      _log("Clear error: $e");
    }
  }

  @override
  Widget build(BuildContext context) {
    final screenSize = MediaQuery.of(context).size;

    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            // Connection Panel
            Container(
              padding: const EdgeInsets.all(12),
              color: Colors.black.withOpacity(0.9),
              child: Row(
                children: [
                  Icon(
                    isConnected ? Icons.wifi : Icons.wifi_off,
                    color: isConnected ? Colors.green : Colors.red,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: _urlController,
                      decoration: InputDecoration(
                        labelText: 'Server URL',
                        labelStyle: const TextStyle(color: Colors.white70, fontSize: 12),
                        border: const OutlineInputBorder(),
                        isDense: true,
                        contentPadding: const EdgeInsets.all(10),
                        suffixIcon: IconButton(
                          icon: const Icon(Icons.refresh, size: 18),
                          onPressed: _testConnection,
                        ),
                      ),
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                      onChanged: (value) => serverUrl = value,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Column(
                    children: [
                      ElevatedButton(
                        onPressed: isConnected && !isStreaming ? _startStream : null,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.green,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        ),
                        child: const Text('Start', style: TextStyle(fontSize: 12)),
                      ),
                      const SizedBox(height: 4),
                      ElevatedButton(
                        onPressed: isStreaming ? _stopStream : null,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.red,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        ),
                        child: const Text('Stop', style: TextStyle(fontSize: 12)),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // AR View
            Expanded(
              child: GestureDetector(
                onTapDown: (details) {
                  _placeDuck(details.localPosition, screenSize);
                },
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    // Camera Feed
                    if (currentFrame != null)
                      Image.memory(
                        currentFrame!,
                        width: double.infinity,
                        height: double.infinity,
                        fit: BoxFit.cover,
                        gaplessPlayback: true,
                      )
                    else
                      Container(
                        color: Colors.black,
                        child: Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              isStreaming
                                  ? const CircularProgressIndicator(color: Colors.blue)
                                  : const Icon(Icons.videocam_off, size: 60, color: Colors.grey),
                              const SizedBox(height: 20),
                              Text(
                                isStreaming ? 'Loading camera...' : 'Press Start',
                                style: const TextStyle(color: Colors.white),
                              ),
                            ],
                          ),
                        ),
                      ),

                    // Stats Overlay
                    if (debugMode)
                      Positioned(
                        top: 10,
                        left: 10,
                        child: Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: Colors.black.withOpacity(0.7),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('FPS: ${fps.toStringAsFixed(1)}',
                                  style: const TextStyle(color: Colors.white, fontSize: 12)),
                              Text('Ducks: ${objects.length}',
                                  style: const TextStyle(color: Colors.yellow, fontSize: 12)),
                              if (grabbedDuckId != null)
                                Text('Grabbed: Duck #$grabbedDuckId',
                                    style: const TextStyle(color: Colors.green, fontSize: 12)),
                            ],
                          ),
                        ),
                      ),

                    // Instructions Overlay
                    if (isStreaming)
                      Positioned(
                        bottom: 10,
                        left: 10,
                        right: 10,
                        child: Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Colors.black.withOpacity(0.7),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                '🎮 HOW TO USE:',
                                style: TextStyle(
                                  color: Colors.yellow,
                                  fontSize: 14,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              const SizedBox(height: 8),
                              const Row(
                                children: [
                                  Icon(Icons.touch_app, color: Colors.white, size: 16),
                                  SizedBox(width: 8),
                                  Text('Tap screen: Place new duck',
                                      style: TextStyle(color: Colors.white, fontSize: 12)),
                                ],
                              ),
                              const SizedBox(height: 4),
                              const Row(
                                children: [
                                  Icon(Icons.front_hand, color: Colors.green, size: 16),
                                  SizedBox(width: 8),
                                  Text('Show hand in camera: Detect hand',
                                      style: TextStyle(color: Colors.white, fontSize: 12)),
                                ],
                              ),
                              const SizedBox(height: 4),
                              const Row(
                                children: [
                                  Icon(Icons.pan_tool, color: Colors.orange, size: 16),
                                  SizedBox(width: 8),
                                  Text('Make fist near duck: Grab duck',
                                      style: TextStyle(color: Colors.white, fontSize: 12)),
                                ],
                              ),
                              const SizedBox(height: 4),
                              const Row(
                                children: [
                                  Icon(Icons.open_in_full, color: Colors.red, size: 16),
                                  SizedBox(width: 8),
                                  Text('Open hand: Release duck',
                                      style: TextStyle(color: Colors.white, fontSize: 12)),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),

                    // Crosshair
                    if (isStreaming)
                      Positioned(
                        top: screenSize.height / 2 - 20,
                        left: screenSize.width / 2 - 20,
                        child: Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            border: Border.all(color: Colors.red, width: 2),
                            shape: BoxShape.circle,
                          ),
                          child: const Center(
                            child: Icon(Icons.add, color: Colors.red, size: 20),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),

            // Controls Panel
            Container(
              padding: const EdgeInsets.all(12),
              color: Colors.black.withOpacity(0.9),
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          children: [
                            const Text('Scale', style: TextStyle(color: Colors.white, fontSize: 12)),
                            Slider(
                              value: scale,
                              min: 0.1,
                              max: 2.0,
                              onChanged: (value) {
                                setState(() => scale = value);
                              },
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          children: [
                            const Text('Rotation', style: TextStyle(color: Colors.white, fontSize: 12)),
                            Slider(
                              value: rotation,
                              min: -pi,
                              max: pi,
                              onChanged: (value) {
                                setState(() => rotation = value);
                              },
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: grabbedDuckId != null ? () => _deleteDuck(grabbedDuckId.toString()) : null,
                          icon: const Icon(Icons.delete, size: 16),
                          label: const Text('Delete Grabbed', style: TextStyle(fontSize: 12)),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.red,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 8),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: _clearAll,
                          icon: const Icon(Icons.delete_sweep, size: 16),
                          label: const Text('Clear All', style: TextStyle(fontSize: 12)),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.orange,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 8),
                          ),
                        ),
                      ),
                      IconButton(
                        icon: Icon(
                          debugMode ? Icons.bug_report : Icons.bug_report_outlined,
                          color: debugMode ? Colors.yellow : Colors.white,
                        ),
                        onPressed: () => setState(() => debugMode = !debugMode),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // Debug Panel
            if (debugMode && debugLogs.isNotEmpty)
              Container(
                height: 80,
                padding: const EdgeInsets.all(8),
                color: Colors.black.withOpacity(0.9),
                child: Column(
                  children: [
                    const Text('Debug', style: TextStyle(color: Colors.yellow, fontSize: 12)),
                    const SizedBox(height: 4),
                    Expanded(
                      child: ListView(
                        reverse: true,
                        children: debugLogs
                            .map((log) => Text(
                          log,
                          style: TextStyle(
                            color: log.contains('✅') ? Colors.green :
                            log.contains('❌') ? Colors.red :
                            Colors.white70,
                            fontSize: 10,
                          ),
                        ))
                            .toList(),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}