#!/usr/bin/env python3
"""
BEAST WEB INTERFACE
===================
Interface web para el asistente de trading.

Uso:
  python beast_web.py
  Luego abre: http://localhost:8080
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
from beast_assistant import BeastAssistant

assistant = BeastAssistant()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BEAST Trading Assistant</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Courier New', monospace;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%);
            min-height: 100vh;
            color: #00ff88;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid #00ff88;
            margin-bottom: 30px;
        }
        
        h1 {
            font-size: 2.5em;
            text-shadow: 0 0 20px #00ff88;
            letter-spacing: 3px;
        }
        
        .subtitle {
            color: #888;
            margin-top: 10px;
        }
        
        .chat-container {
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid #333;
            border-radius: 10px;
            padding: 20px;
            min-height: 400px;
            max-height: 500px;
            overflow-y: auto;
            margin-bottom: 20px;
        }
        
        .message {
            margin-bottom: 20px;
            padding: 15px;
            border-radius: 8px;
        }
        
        .user-msg {
            background: rgba(0, 100, 255, 0.2);
            border-left: 4px solid #0066ff;
        }
        
        .bot-msg {
            background: rgba(0, 255, 136, 0.1);
            border-left: 4px solid #00ff88;
        }
        
        .message-label {
            font-size: 0.8em;
            color: #666;
            margin-bottom: 5px;
        }
        
        .message-content {
            white-space: pre-wrap;
            font-size: 0.9em;
            line-height: 1.5;
        }
        
        .input-container {
            display: flex;
            gap: 10px;
        }
        
        #query-input {
            flex: 1;
            padding: 15px;
            font-size: 1.1em;
            background: rgba(0, 0, 0, 0.7);
            border: 2px solid #333;
            border-radius: 8px;
            color: #fff;
            font-family: inherit;
        }
        
        #query-input:focus {
            outline: none;
            border-color: #00ff88;
            box-shadow: 0 0 10px rgba(0, 255, 136, 0.3);
        }
        
        #send-btn {
            padding: 15px 30px;
            font-size: 1.1em;
            background: linear-gradient(135deg, #00ff88, #00cc6a);
            border: none;
            border-radius: 8px;
            color: #000;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        #send-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 0 20px rgba(0, 255, 136, 0.5);
        }
        
        #send-btn:disabled {
            background: #333;
            color: #666;
            cursor: not-allowed;
            transform: none;
        }
        
        .quick-btns {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .quick-btn {
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid #444;
            border-radius: 20px;
            color: #aaa;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .quick-btn:hover {
            background: rgba(0, 255, 136, 0.2);
            border-color: #00ff88;
            color: #00ff88;
        }
        
        .status {
            text-align: center;
            padding: 10px;
            color: #666;
            font-size: 0.9em;
        }
        
        .status.live {
            color: #00ff88;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #333;
            border-top-color: #00ff88;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .bullish { color: #00ff88; }
        .bearish { color: #ff4444; }
        .neutral { color: #ffaa00; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>BEAST ASSISTANT</h1>
            <p class="subtitle">Trading Intelligence - Jetson Powered</p>
        </header>
        
        <div class="quick-btns">
            <button class="quick-btn" onclick="sendQuery('analiza SPY')">SPY</button>
            <button class="quick-btn" onclick="sendQuery('analiza QQQ')">QQQ</button>
            <button class="quick-btn" onclick="sendQuery('analiza TSLA')">TSLA</button>
            <button class="quick-btn" onclick="sendQuery('analiza NVDA')">NVDA</button>
            <button class="quick-btn" onclick="sendQuery('flow SPY')">Flow SPY</button>
            <button class="quick-btn" onclick="sendQuery('ayuda')">Ayuda</button>
        </div>
        
        <div class="chat-container" id="chat">
            <div class="message bot-msg">
                <div class="message-label">BEAST</div>
                <div class="message-content">Hola! Soy tu asistente de trading.

Preguntame sobre cualquier stock:
- "analiza SPY"
- "flow QQQ"  
- "SPY put 690"
- "llegara a 688?"

Datos en TIEMPO REAL.</div>
            </div>
        </div>
        
        <div class="input-container">
            <input type="text" id="query-input" placeholder="Escribe tu pregunta... (ej: analiza SPY)" 
                   onkeypress="if(event.key==='Enter')sendQuery()">
            <button id="send-btn" onclick="sendQuery()">ENVIAR</button>
        </div>
        
        <div class="status live" id="status">
            ● CONECTADO - Datos en vivo
        </div>
    </div>
    
    <script>
        const chat = document.getElementById('chat');
        const input = document.getElementById('query-input');
        const btn = document.getElementById('send-btn');
        const status = document.getElementById('status');
        
        function addMessage(content, isUser) {
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user-msg' : 'bot-msg');
            div.innerHTML = `
                <div class="message-label">${isUser ? 'TU' : 'BEAST'}</div>
                <div class="message-content">${escapeHtml(content)}</div>
            `;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }
        
        function escapeHtml(text) {
            return text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }
        
        async function sendQuery(query) {
            query = query || input.value.trim();
            if (!query) return;
            
            addMessage(query, true);
            input.value = '';
            btn.disabled = true;
            status.innerHTML = '<span class="loading"></span> Analizando...';
            status.className = 'status';
            
            try {
                const response = await fetch('/query', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: query})
                });
                const data = await response.json();
                addMessage(data.response, false);
            } catch (e) {
                addMessage('Error de conexion: ' + e.message, false);
            }
            
            btn.disabled = false;
            status.innerHTML = '● CONECTADO - Datos en vivo';
            status.className = 'status live';
            input.focus();
        }
    </script>
</body>
</html>
"""

class BeastHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silenciar logs
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(HTML_TEMPLATE.encode())
    
    def do_POST(self):
        if self.path == '/query':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())
            
            query = data.get('query', '')
            response = assistant.process_query(query)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'response': response}).encode())
        else:
            self.send_response(404)
            self.end_headers()


def main():
    port = 8080
    server = HTTPServer(('0.0.0.0', port), BeastHandler)
    
    print("=" * 50)
    print("  BEAST WEB ASSISTANT")
    print("=" * 50)
    print()
    print(f"  Servidor corriendo en:")
    print(f"  http://localhost:{port}")
    print()
    print("  Presiona Ctrl+C para detener")
    print("=" * 50)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        server.shutdown()


if __name__ == "__main__":
    main()
