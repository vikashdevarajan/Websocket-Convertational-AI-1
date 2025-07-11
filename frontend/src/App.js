import React, { useState, useRef, useEffect } from 'react';
import './App.css';

const App = () => {
    // State Management
    const [isListening, setIsListening] = useState(false);
    const [connectionStatus, setConnectionStatus] = useState('Disconnected');
    const [speechStatus, setSpeechStatus] = useState('');
    const [transcript, setTranscript] = useState('');
    const [llmResponse, setLlmResponse] = useState('');
    const [audioUrl, setAudioUrl] = useState(null);
    const [processingStatus, setProcessingStatus] = useState('');
    const [speechDetected, setSpeechDetected] = useState(false); // New state for speech detection

    // Refs
    const socketRef = useRef(null);
    const mediaStreamRef = useRef(null);
    const processorRef = useRef(null);
    const audioContextRef = useRef(null);
    const audioRef = useRef(null); // Add a ref for the audio element

    // WebSocket connection
    const connectWebSocket = () => {
        const wsUrl = `ws://${window.location.hostname}:8000/ws`;
        socketRef.current = new WebSocket(wsUrl);

        socketRef.current.onopen = () => {
            console.log('🔗 WebSocket connected');
            setConnectionStatus('Connected');
        };

        socketRef.current.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (e) {
                console.error('❌ Error parsing WebSocket message:', e);
            }
        };

        socketRef.current.onclose = () => {
            console.log('🔌 WebSocket disconnected');
            setConnectionStatus('Disconnected');
            if (isListening) {
                stopListening();
            }
        };

        socketRef.current.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
            setConnectionStatus('Error');
        };
    };

    const handleWebSocketMessage = (data) => {
        console.log('📨 Received:', data);

        switch (data.type) {
            case 'connection':
                setConnectionStatus(`Connected (${data.session_id})`);
                break;

            case 'speech_start':
                setSpeechDetected(true);
                setSpeechStatus('🎤 Speech detected!');
                setTranscript('Listening...');
                break;

            case 'speech_active':
                setSpeechStatus(`🎤 Speaking... (${data.duration_chunks} chunks)`);
                break;

            case 'speech_end':
                setSpeechDetected(false);
                setSpeechStatus('🛑 Speech ended, processing...');
                break;

            case 'processing':
                setProcessingStatus(data.message);
                break;

            case 'response':
                setSpeechStatus('');
                setProcessingStatus('');
                setTranscript(data.stt || '');
                setLlmResponse(data.llm || '');
                
                if (data.tts) {
                    const audioBlob = base64ToBlob(data.tts, 'audio/wav');
                    const url = URL.createObjectURL(audioBlob);
                    setAudioUrl(url);

                    // Play audio automatically
                    setTimeout(() => {
                        if (audioRef.current) {
                            audioRef.current.play().catch(e => console.log('Audio play error:', e));
                        }
                    }, 100); // slight delay to ensure src is set
                }
                break;

            case 'notification':
                setSpeechStatus('');
                setProcessingStatus('');
                setTranscript(data.message);
                break;

            case 'error':
                setSpeechStatus('');
                setProcessingStatus('');
                console.error('Server error:', data.message);
                break;

            default:
                console.log('Unknown message type:', data.type);
        }
    };

    const base64ToBlob = (base64, mimeType) => {
        const byteCharacters = atob(base64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        return new Blob([byteArray], { type: mimeType });
    };

    const startListening = async () => {
        try {
            // Get microphone access
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaStreamRef.current = stream;

            // Setup audio processing
            audioContextRef.current = new AudioContext({ sampleRate: 16000 });
            const source = audioContextRef.current.createMediaStreamSource(stream);
            processorRef.current = audioContextRef.current.createScriptProcessor(4096, 1, 1);

            // Process audio and send to WebSocket
            processorRef.current.onaudioprocess = (e) => {
                if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
                    const floatAudio = e.inputBuffer.getChannelData(0);
                    
                    // Convert to 16-bit PCM
                    const pcmBuffer = new Int16Array(floatAudio.length);
                    for (let i = 0; i < floatAudio.length; i++) {
                        pcmBuffer[i] = Math.max(-32768, Math.min(32767, Math.round(floatAudio[i] * 32767)));
                    }
                    
                    // Send binary data
                    socketRef.current.send(pcmBuffer.buffer);
                }
            };

            source.connect(processorRef.current);
            processorRef.current.connect(audioContextRef.current.destination);

            setIsListening(true);
            setSpeechStatus('🎧 Listening for speech...');
            
        } catch (error) {
            console.error('❌ Error starting audio:', error);
            alert('Could not access microphone. Please check permissions.');
        }
    };

    const stopListening = () => {
        if (mediaStreamRef.current) {
            mediaStreamRef.current.getTracks().forEach(track => track.stop());
            mediaStreamRef.current = null;
        }
        
        if (processorRef.current) {
            processorRef.current.disconnect();
            processorRef.current = null;
        }
        
        if (audioContextRef.current) {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }

        setIsListening(false);
        setSpeechStatus('');
        setProcessingStatus('');
    };

    // Initialize WebSocket on component mount
    useEffect(() => {
        connectWebSocket();
        return () => {
            if (socketRef.current) {
                socketRef.current.close();
            }
            stopListening();
        };
    }, []);

    return (
        <div className="App">
            <header className="App-header custom-chat-header">
                <h1 className="main-title">CONVERSATIONAL AI</h1>
                <div className="chat-container">
                    <div className="chat-section user-section">
                        <div className="chat-label">you said</div>
                        <div className="chat-bubble user-bubble small-bubble">
                            {transcript && transcript !== 'Listening...'
                                ? transcript
                                : (isListening ? 'Listening...' : 'No speech detected')}
                        </div>
                    </div>
                    {/* Floating speech indicator */}
                    {speechDetected && (
                        <div className="speech-floating-indicator">
                            <span className="dot"></span>
                        </div>
                    )}
                    <div className="chat-section ai-section">
                        <div className="chat-label ai-label">AI assistant's Reply</div>
                        <div className="chat-bubble ai-bubble">
                            {processingStatus ? (
                                <span className="ai-typing">
                                    <span className="dot"></span>
                                    <span className="dot"></span>
                                    <span className="dot"></span>
                                </span>
                            ) : (
                                llmResponse || 'Waiting for response...'
                            )}
                        </div>
                    </div>
                    <div className="audio-section">
                        {audioUrl && (
                            <audio ref={audioRef} src={audioUrl} />
                        )}
                        {processingStatus && (
                            <span className="ai-speaking-animation">
                                <span className="dot"></span>
                                <span className="dot"></span>
                                <span className="dot"></span>
                            </span>
                        )}
                    </div>
                </div>
                <div className="controls-bar">
                    <button 
                        onClick={isListening ? stopListening : startListening}
                        className={`control-button ${isListening ? 'stop' : 'start'}`}
                        disabled={!connectionStatus.includes('Connected') && !isListening}
                    >
                        {isListening ? 'Stop Listening' : 'Start Listening'}
                    </button>
                    <span className={`status-indicator ${connectionStatus.includes('Connected') ? 'connected' : 'disconnected'}`}>
                        {connectionStatus.includes('Connected') ? `WebSocket: ${connectionStatus}` : 'WebSocket: Disconnected'}
                    </span>
                </div>
            </header>
        </div>
    );
};

export default App;