import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'app.dart';

// ISOLATED ENTRYPOINT FOR iOS LOCAL TESTING
// Run with: flutter run -t lib/main_ios_isolated.dart -d ios
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // We load a mock environment to force local LiveKit connection
  // bypassing the default LiveKit Cloud Sandbox.
  await dotenv.load(fileName: 'assets/.env', isOptional: true);
  
  // Overriding env for local iOS testing on physical device (must use Mac's local IP)
  // (now loaded directly from assets/.env)
  
  // You would ideally generate a token and place it here, 
  // or update app_ctrl.dart to accept LIVEKIT_URL directly.
  
  runApp(const VoiceAssistantApp());
}
