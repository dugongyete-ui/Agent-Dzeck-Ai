import React, { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import axios from "axios";
import "./App.css";
import faviconPng from "./logo.png";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

function App() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeView, setActiveView] = useState("chat");
  const [responseData, setResponseData] = useState(null);
  const [isOnline, setIsOnline] = useState(false);
  const [status, setStatus] = useState("Agent siap");
  const [expandedReasoning, setExpandedReasoning] = useState(new Set());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [modelConfig, setModelConfig] = useState(null);
  const [selectedProvider, setSelectedProvider] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [isChangingModel, setIsChangingModel] = useState(false);
  const [showModelSelector, setShowModelSelector] = useState(false);
  const [previewFiles, setPreviewFiles] = useState([]);
  const [selectedPreviewFile, setSelectedPreviewFile] = useState("");
  const [wsStatus, setWsStatus] = useState("disconnected");
  const [realtimeProgress, setRealtimeProgress] = useState(0);
  const [realtimeDetails, setRealtimeDetails] = useState("");
  const [projectFiles, setProjectFiles] = useState([]);
  const [selectedFileContent, setSelectedFileContent] = useState(null);
  const [editorContent, setEditorContent] = useState(null);
  const [editorModified, setEditorModified] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);
  const [activeAgentType, setActiveAgentType] = useState(null);
  const messagesEndRef = useRef(null);
  const wsRef = useRef(null);
  const previewIframeRef = useRef(null);

  const connectWebSocket = useCallback(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = BACKEND_URL ? new URL(BACKEND_URL).host : window.location.host;
    const wsUrl = `${wsProtocol}//${wsHost}/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus("connected");
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          } else {
            clearInterval(pingInterval);
          }
        }, 30000);
        ws._pingInterval = pingInterval;
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          switch (msg.type) {
            case "status":
              setStatus(msg.status || "");
              setRealtimeProgress(msg.progress || 0);
              setRealtimeDetails(msg.details || "");
              if (msg.progress >= 1.0) {
                setTimeout(() => setActiveAgentType(null), 10000);
              }
              break;
            case "agent_switch":
              setActiveAgentType(msg.agent_type);
              if (msg.agent_type === "browser_agent") {
                setActiveView("browser");
                fetchScreenshot();
              } else if (msg.agent_type === "code_agent") {
                setActiveView("preview");
              }
              break;
            case "execution":
              break;
            case "file_update":
              fetchPreviewFiles();
              fetchProjectFiles();
              break;
            case "preview_ready":
              fetchPreviewFiles();
              if (msg.preview_url) {
                setSelectedPreviewFile(msg.preview_url.replace("/api/preview/", ""));
              }
              setActiveView("preview");
              break;
            case "pong":
              break;
            default:
              break;
          }
        } catch (e) {
          console.error("WebSocket message parse error:", e);
        }
      };

      ws.onclose = () => {
        setWsStatus("disconnected");
        if (ws._pingInterval) clearInterval(ws._pingInterval);
        setTimeout(() => connectWebSocket(), 3000);
      };

      ws.onerror = () => {
        setWsStatus("error");
      };
    } catch (e) {
      console.error("WebSocket connection error:", e);
      setTimeout(() => connectWebSocket(), 5000);
    }
  }, []);

  const fetchModelConfig = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/config/models`);
      setModelConfig(res.data);
      setSelectedProvider(res.data.current_provider);
      setSelectedModel(res.data.current_model);
    } catch (err) {
      console.error("Error fetching model config:", err);
    }
  }, []);

  const fetchPreviewFiles = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/preview-files`);
      setPreviewFiles(res.data.files || []);
      if (res.data.files?.length > 0 && !selectedPreviewFile) {
        const idx = res.data.files.indexOf("index.html");
        setSelectedPreviewFile(idx >= 0 ? "index.html" : res.data.files[0]);
      }
    } catch (err) {
      console.error("Error fetching preview files:", err);
    }
  }, [selectedPreviewFile]);

  const fetchProjectFiles = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/project-files`);
      setProjectFiles(res.data.files || []);
    } catch (err) {
      console.error("Error fetching project files:", err);
    }
  }, []);

  const fetchFileContent = async (filePath) => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/file-content/${filePath}`);
      setSelectedFileContent({ file: filePath, content: res.data.content, size: res.data.size });
    } catch (err) {
      console.error("Error fetching file content:", err);
    }
  };

  const fetchEditorFileContent = async (filePath) => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/file-content/${filePath}`);
      setEditorContent({ file: filePath, content: res.data.content, size: res.data.size });
      setEditorModified(false);
      setSaveStatus(null);
    } catch (err) {
      console.error("Error fetching file content:", err);
    }
  };

  const handleSaveFile = async () => {
    if (!editorContent || !editorModified) return;
    setIsSaving(true);
    setSaveStatus(null);
    try {
      await axios.put(`${BACKEND_URL}/api/file-content/${editorContent.file}`, {
        content: editorContent.content
      });
      setEditorModified(false);
      setSaveStatus("saved");
      fetchProjectFiles();
      fetchPreviewFiles();
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (err) {
      console.error("Error saving file:", err);
      setSaveStatus("error");
      setTimeout(() => setSaveStatus(null), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  const handleEditorKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      handleSaveFile();
    }
    if (e.key === "Tab") {
      e.preventDefault();
      const start = e.target.selectionStart;
      const end = e.target.selectionEnd;
      const val = e.target.value;
      const newVal = val.substring(0, start) + "  " + val.substring(end);
      setEditorContent(prev => ({ ...prev, content: newVal }));
      setEditorModified(true);
      setTimeout(() => {
        e.target.selectionStart = e.target.selectionEnd = start + 2;
      }, 0);
    }
  };

  const handleModelChange = async () => {
    if (!selectedProvider || !selectedModel) return;
    if (modelConfig && selectedProvider === modelConfig.current_provider && selectedModel === modelConfig.current_model) {
      setShowModelSelector(false);
      return;
    }
    setIsChangingModel(true);
    try {
      await axios.post(`${BACKEND_URL}/api/config/update`, {
        provider_name: selectedProvider,
        model: selectedModel
      });
      await fetchModelConfig();
      setShowModelSelector(false);
      setMessages(prev => [...prev, {
        type: "agent",
        content: `Model berhasil diganti ke **${selectedProvider}** - \`${selectedModel}\``,
        agentName: "System",
        status: "Model diperbarui"
      }]);
    } catch (err) {
      console.error("Error updating model:", err);
      setError("Gagal mengganti model. Pastikan API key tersedia.");
    } finally {
      setIsChangingModel(false);
    }
  };

  const fetchLatestAnswer = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/latest_answer`);
      const data = res.data;
      updateData(data);
      if (!data.answer || data.answer.trim() === "") return;
      const normalizedNewAnswer = normalizeAnswer(data.answer);
      const answerExists = messages.some(
        (msg) => normalizeAnswer(msg.content) === normalizedNewAnswer
      );
      if (!answerExists) {
        setMessages((prev) => [
          ...prev,
          {
            type: "agent",
            content: data.answer,
            reasoning: data.reasoning,
            agentName: data.agent_name,
            status: data.status,
            uid: data.uid,
          },
        ]);
        setStatus(data.status);
        scrollToBottom();
        fetchPreviewFiles();
        fetchProjectFiles();
      }
    } catch (error) {
      console.error("Error fetching latest answer:", error);
    }
  }, [messages, fetchPreviewFiles, fetchProjectFiles]);

  useEffect(() => {
    checkHealth();
    fetchModelConfig();
    fetchPreviewFiles();
    fetchProjectFiles();
    connectWebSocket();
    const healthInterval = setInterval(checkHealth, 10000);
    return () => {
      clearInterval(healthInterval);
      if (wsRef.current) {
        if (wsRef.current._pingInterval) clearInterval(wsRef.current._pingInterval);
        wsRef.current.close();
      }
    };
  }, [fetchModelConfig, connectWebSocket, fetchPreviewFiles, fetchProjectFiles]);

  useEffect(() => {
    const pollInterval = setInterval(() => {
      if (isLoading) {
        fetchLatestAnswer();
      }
    }, 5000);
    return () => clearInterval(pollInterval);
  }, [isLoading, fetchLatestAnswer]);

  useEffect(() => {
    if (activeView === "browser" || activeAgentType === "browser_agent") {
      fetchScreenshot();
      const screenshotInterval = setInterval(() => {
        fetchScreenshot();
      }, 3000);
      return () => clearInterval(screenshotInterval);
    }
  }, [activeView, activeAgentType, isLoading]);

  const checkHealth = async () => {
    try {
      await axios.get(`${BACKEND_URL}/health`);
      setIsOnline(true);
    } catch {
      setIsOnline(false);
    }
  };

  const fetchScreenshot = async () => {
    try {
      const timestamp = new Date().getTime();
      const res = await axios.get(
        `${BACKEND_URL}/screenshots/updated_screen.png?timestamp=${timestamp}`,
        { responseType: "blob" }
      );
      const imageUrl = URL.createObjectURL(res.data);
      setResponseData((prev) => {
        if (prev?.screenshot && prev.screenshot !== "placeholder.png") {
          URL.revokeObjectURL(prev.screenshot);
        }
        return { ...prev, screenshot: imageUrl, screenshotTimestamp: new Date().getTime() };
      });
    } catch (err) {
      setResponseData((prev) => ({
        ...prev,
        screenshot: null,
        screenshotTimestamp: new Date().getTime(),
      }));
    }
  };

  const normalizeAnswer = (answer) => {
    return answer.trim().toLowerCase().replace(/\s+/g, " ").replace(/[.,!?]/g, "");
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const toggleReasoning = (messageIndex) => {
    setExpandedReasoning((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(messageIndex)) newSet.delete(messageIndex);
      else newSet.add(messageIndex);
      return newSet;
    });
  };

  const updateData = (data) => {
    setResponseData((prev) => ({
      ...prev,
      blocks: data.blocks || prev?.blocks || null,
      done: data.done,
      answer: data.answer,
      agent_name: data.agent_name,
      status: data.status,
      uid: data.uid,
    }));
  };

  const handleStop = async (e) => {
    e.preventDefault();
    setIsLoading(false);
    setError(null);
    try {
      await axios.get(`${BACKEND_URL}/stop`);
      setStatus("Menghentikan proses...");
    } catch (err) {
      console.error("Error stopping:", err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    const userQuery = query;
    setMessages((prev) => [...prev, { type: "user", content: userQuery }]);
    setIsLoading(true);
    setError(null);
    setQuery("");

    try {
      const res = await axios.post(`${BACKEND_URL}/query`, {
        query: userQuery,
        tts_enabled: false,
      });
      updateData(res.data);
      if (res.data && res.data.answer) {
        const normalizedNewAnswer = normalizeAnswer(res.data.answer);
        const answerExists = messages.some(
          (msg) => normalizeAnswer(msg.content) === normalizedNewAnswer
        );
        if (!answerExists) {
          setMessages((prev) => [
            ...prev,
            {
              type: "agent",
              content: res.data.answer,
              reasoning: res.data.reasoning,
              agentName: res.data.agent_name || "Agent",
              status: res.data.status,
              uid: res.data.uid,
            },
          ]);
        }
      }
      fetchPreviewFiles();
      fetchProjectFiles();
    } catch (err) {
      console.error("Error:", err);
      const errData = err.response?.data;
      let errorMsg = "Gagal memproses pesan.";
      let errorContent = "Error: Tidak bisa mendapatkan respon.";
      if (errData && errData.answer) {
        errorContent = errData.answer;
        errorMsg = errData.answer.substring(0, 100);
      } else if (err.response?.status === 503) {
        errorContent = "Sistem belum siap. Silakan tunggu beberapa saat dan coba lagi.";
        errorMsg = "Sistem belum siap";
      } else if (err.response?.status === 429) {
        errorContent = "Terlalu banyak permintaan. Tunggu proses sebelumnya selesai.";
        errorMsg = "Terlalu banyak permintaan";
      }
      setError(errorMsg);
      setMessages((prev) => [
        ...prev,
        { type: "error", content: errorContent },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = async () => {
    try {
      await axios.post(`${BACKEND_URL}/new_project`);
    } catch (err) {
      console.error("Error creating new project:", err);
    }
    setMessages([]);
    setResponseData(null);
    setError(null);
    setStatus("Agent siap");
    setQuery("");
    setPreviewFiles([]);
    setSelectedPreviewFile("");
    setProjectFiles([]);
    setSelectedFileContent(null);
    setEditorContent(null);
    setEditorModified(false);
    setSaveStatus(null);
    setRealtimeProgress(0);
    setRealtimeDetails("");
    setActiveAgentType(null);
  };

  const handleClearHistory = async () => {
    try {
      await axios.post(`${BACKEND_URL}/clear_history`);
    } catch (err) {
      console.error("Error clearing history:", err);
    }
    setMessages([]);
    setResponseData(null);
    setError(null);
    setStatus("Riwayat dihapus");
  };

  const handleDownloadZip = async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/download-zip`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "agent-dzeck-project.zip");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Error downloading zip:", err);
      if (err.response?.status === 404) {
        setError("Belum ada file project. Minta AI untuk membuat project terlebih dahulu.");
      } else {
        setError("Gagal mengunduh project. Coba lagi nanti.");
      }
    }
  };

  const handleDownloadFile = async (filePath) => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/file-content/${filePath}`);
      const blob = new Blob([res.data.content], { type: "text/plain" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", filePath.split("/").pop());
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Error downloading file:", err);
      setError("Gagal mengunduh file.");
    }
  };

  const refreshPreview = () => {
    if (previewIframeRef.current) {
      previewIframeRef.current.src = previewIframeRef.current.src;
    }
  };

  const navItems = [
    {
      id: "chat",
      label: "Chat",
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      ),
    },
    {
      id: "preview",
      label: "Preview",
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
          <line x1="8" y1="21" x2="16" y2="21"/>
          <line x1="12" y1="17" x2="12" y2="21"/>
        </svg>
      ),
    },
    {
      id: "editor",
      label: "Editor",
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="16 18 22 12 16 6"/>
          <polyline points="8 6 2 12 8 18"/>
        </svg>
      ),
    },
    {
      id: "files",
      label: "Files",
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
      ),
    },
    {
      id: "browser",
      label: "Browser",
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="2" y1="12" x2="22" y2="12"/>
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
        </svg>
      ),
    },
  ];

  const currentProviderModels = modelConfig?.providers?.[selectedProvider]?.models || [];

  const getFileIcon = (filename) => {
    const ext = filename.split('.').pop().toLowerCase();
    const iconMap = {
      'html': '#e44d26', 'css': '#264de4', 'js': '#f7df1e',
      'jsx': '#61dafb', 'ts': '#3178c6', 'tsx': '#3178c6',
      'py': '#3776ab', 'json': '#292929', 'md': '#083fa1',
      'txt': '#666', 'svg': '#ffb13b', 'go': '#00add8',
      'rs': '#dea584', 'java': '#b07219', 'cpp': '#f34b7d',
      'c': '#555555', 'sh': '#89e051', 'yml': '#cb171e',
      'yaml': '#cb171e', 'toml': '#9c4121', 'ini': '#d1dbe0',
    };
    return iconMap[ext] || '#888';
  };

  const getFileExtIcon = (filename) => {
    const ext = filename.split('.').pop().toLowerCase();
    const emojiMap = {
      'html': '🌐', 'css': '🎨', 'js': '⚡', 'jsx': '⚛️',
      'ts': '📘', 'tsx': '📘', 'py': '🐍', 'json': '📋',
      'md': '📝', 'txt': '📄', 'svg': '🖼️', 'go': '🔵',
      'sh': '💻', 'yml': '⚙️', 'yaml': '⚙️', 'ini': '⚙️',
    };
    return emojiMap[ext] || '📄';
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getLineNumbers = (content) => {
    if (!content) return "";
    const lines = content.split("\n");
    return lines.map((_, i) => i + 1).join("\n");
  };

  return (
    <div className="app-container">
      <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <img src={faviconPng} alt="Agent Dzeck AI" className="sidebar-logo-img" />
            {!sidebarCollapsed && <span className="sidebar-title">Agent Dzeck AI</span>}
          </div>
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? "Perluas" : "Kecilkan"}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {sidebarCollapsed ? (
                <polyline points="9 18 15 12 9 6"/>
              ) : (
                <polyline points="15 18 9 12 15 6"/>
              )}
            </svg>
          </button>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${activeView === item.id ? "active" : ""}`}
              onClick={() => { setActiveView(item.id); setMobileMenuOpen(false); }}
              title={item.label}
            >
              <span className="nav-icon">{item.icon}</span>
              {!sidebarCollapsed && <span className="nav-label">{item.label}</span>}
            </button>
          ))}
        </nav>

        {!sidebarCollapsed && (
          <div className="model-selector-section">
            <button
              className="model-selector-toggle"
              onClick={() => setShowModelSelector(!showModelSelector)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
              <span>Model AI</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginLeft: 'auto', transform: showModelSelector ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s'}}>
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>

            {showModelSelector && modelConfig && (
              <div className="model-selector-panel">
                <div className="model-current-info">
                  <span className="model-current-label">Aktif:</span>
                  <span className="model-current-value">{modelConfig.current_model}</span>
                </div>

                <label className="model-field-label">Provider</label>
                <select
                  className="model-select"
                  value={selectedProvider}
                  onChange={(e) => {
                    const newProvider = e.target.value;
                    setSelectedProvider(newProvider);
                    const models = modelConfig.providers[newProvider]?.models || [];
                    if (models.length > 0) setSelectedModel(models[0]);
                  }}
                >
                  {Object.entries(modelConfig.providers).map(([key, val]) => (
                    <option key={key} value={key}>{val.name}</option>
                  ))}
                </select>

                <label className="model-field-label">Model</label>
                <select
                  className="model-select"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                >
                  {currentProviderModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>

                <button
                  className="model-apply-btn"
                  onClick={handleModelChange}
                  disabled={isChangingModel}
                >
                  {isChangingModel ? "Mengganti..." : "Terapkan"}
                </button>
              </div>
            )}
          </div>
        )}

        <div className="sidebar-actions">
          <button className="sidebar-action-btn new-chat-btn" onClick={handleNewChat} title="Chat Baru">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            {!sidebarCollapsed && <span>Chat Baru</span>}
          </button>
          <button className="sidebar-action-btn clear-btn" onClick={handleClearHistory} title="Hapus Riwayat">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
            {!sidebarCollapsed && <span>Hapus Riwayat</span>}
          </button>
          <button className="sidebar-action-btn download-btn" onClick={handleDownloadZip} title="Unduh Project (.zip)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            {!sidebarCollapsed && <span>Unduh .ZIP</span>}
          </button>
        </div>

        <div className="sidebar-footer">
          <div className={`status-badge ${isOnline ? "online" : "offline"}`}>
            <div className="status-dot-small" />
            {!sidebarCollapsed && (
              <span>{isOnline ? "Online" : "Offline"}</span>
            )}
          </div>
          {!sidebarCollapsed && wsStatus === "connected" && (
            <div className="ws-badge">
              <div className="ws-dot" />
              <span>Live</span>
            </div>
          )}
        </div>
      </aside>

      <div className="mobile-header">
        <button className="mobile-menu-btn" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <div className="mobile-brand">
          <img src={faviconPng} alt="Agent Dzeck AI" className="mobile-logo" />
          <span>Agent Dzeck AI</span>
        </div>
        <div className={`status-badge small ${isOnline ? "online" : "offline"}`}>
          <div className="status-dot-small" />
        </div>
      </div>

      {mobileMenuOpen && (
        <div className="mobile-overlay" onClick={() => setMobileMenuOpen(false)}>
          <div className="mobile-drawer" onClick={(e) => e.stopPropagation()}>
            <nav className="mobile-nav">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  className={`mobile-nav-item ${activeView === item.id ? "active" : ""}`}
                  onClick={() => { setActiveView(item.id); setMobileMenuOpen(false); }}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
              <hr className="mobile-divider" />
              <button className="mobile-nav-item" onClick={() => { handleNewChat(); setMobileMenuOpen(false); }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                <span>Chat Baru</span>
              </button>
              <button className="mobile-nav-item danger" onClick={() => { handleClearHistory(); setMobileMenuOpen(false); }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                <span>Hapus Riwayat</span>
              </button>
              <button className="mobile-nav-item download" onClick={() => { handleDownloadZip(); setMobileMenuOpen(false); }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                <span>Unduh Project .ZIP</span>
              </button>
            </nav>
          </div>
        </div>
      )}

      <main className="main-content">
        {(isLoading || realtimeProgress > 0) && (
          <div className="progress-bar-container">
            <div className="progress-bar" style={{ width: `${Math.max(realtimeProgress * 100, isLoading ? 5 : 0)}%` }} />
            <div className="progress-info">
              {realtimeDetails && <span className="progress-label">{realtimeDetails}</span>}
              {isLoading && <span className="progress-percent">{Math.round(realtimeProgress * 100)}%</span>}
            </div>
          </div>
        )}

        {activeView === "chat" && (
          <div className="chat-panel">
            <div className="panel-header">
              <h2>Chat AI Agent</h2>
              <div className="panel-header-right">
                {modelConfig && (
                  <button
                    className="model-badge model-badge-btn"
                    title="Klik untuk ganti model AI"
                    onClick={() => setShowModelSelector(!showModelSelector)}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                    {modelConfig.current_provider}/{modelConfig.current_model.length > 20
                      ? modelConfig.current_model.substring(0, 20) + "..."
                      : modelConfig.current_model}
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginLeft: '4px'}}>
                      <polyline points="6 9 12 15 18 9"/>
                    </svg>
                  </button>
                )}
                <span className="panel-badge">{status}</span>
              </div>
            </div>
            {showModelSelector && modelConfig && (
              <div className="inline-model-selector">
                <div className="inline-model-row">
                  <label>Provider:</label>
                  <select
                    className="model-select"
                    value={selectedProvider}
                    onChange={(e) => {
                      const newProvider = e.target.value;
                      setSelectedProvider(newProvider);
                      const models = modelConfig.providers[newProvider]?.models || [];
                      if (models.length > 0) setSelectedModel(models[0]);
                    }}
                  >
                    {Object.entries(modelConfig.providers).map(([key, val]) => (
                      <option key={key} value={key}>{val.name}</option>
                    ))}
                  </select>
                  <label>Model:</label>
                  <select
                    className="model-select"
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                  >
                    {currentProviderModels.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <button
                    className="model-apply-btn"
                    onClick={handleModelChange}
                    disabled={isChangingModel}
                  >
                    {isChangingModel ? "..." : "Terapkan"}
                  </button>
                  <button
                    className="model-close-btn"
                    onClick={() => setShowModelSelector(false)}
                  >
                    &times;
                  </button>
                </div>
              </div>
            )}
            <div className="messages-container">
              {messages.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">
                    <img src={faviconPng} alt="Agent Dzeck AI" className="empty-logo" />
                  </div>
                  <h3>Selamat Datang di Agent Dzeck AI</h3>
                  <p>AI Agent full-stack siap membantu Anda membuat website, aplikasi, dan banyak lagi.</p>
                  {modelConfig && (
                    <p className="empty-hint">Model aktif: {modelConfig.providers[modelConfig.current_provider]?.name} - {modelConfig.current_model}</p>
                  )}
                  <div className="quick-actions">
                    <button className="quick-btn" onClick={() => { setQuery("Buatkan website portfolio modern"); }}>
                      <span className="quick-icon">🌐</span> Website Portfolio
                    </button>
                    <button className="quick-btn" onClick={() => { setQuery("Buatkan kalkulator web dengan design menarik"); }}>
                      <span className="quick-icon">🧮</span> Kalkulator Web
                    </button>
                    <button className="quick-btn" onClick={() => { setQuery("Buatkan to-do list app dengan local storage"); }}>
                      <span className="quick-icon">📝</span> To-Do App
                    </button>
                    <button className="quick-btn" onClick={() => { setQuery("Buatkan landing page startup modern"); }}>
                      <span className="quick-icon">🚀</span> Landing Page
                    </button>
                  </div>
                </div>
              ) : (
                messages.map((msg, index) => (
                  <div
                    key={index}
                    className={`message ${msg.type === "user" ? "user-msg" : msg.type === "agent" ? "agent-msg" : "error-msg"}`}
                  >
                    {msg.type === "agent" && (
                      <div className="msg-meta">
                        <span className="agent-badge">{msg.agentName}</span>
                        {msg.reasoning && (
                          <button className="reasoning-btn" onClick={() => toggleReasoning(index)}>
                            {expandedReasoning.has(index) ? "🔽 Sembunyikan" : "💡 Lihat"} Alasan
                          </button>
                        )}
                      </div>
                    )}
                    {msg.type === "agent" && msg.reasoning && expandedReasoning.has(index) && (
                      <div className="reasoning-box">
                        <ReactMarkdown>{msg.reasoning}</ReactMarkdown>
                      </div>
                    )}
                    <div className="msg-body">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                ))
              )}
              {isLoading && (
                <div className="typing-indicator">
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                  {realtimeDetails && <span className="typing-status">{realtimeDetails}</span>}
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <form onSubmit={handleSubmit} className="chat-input-form">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ketik pesan Anda di sini..."
                disabled={isLoading}
              />
              <div className="chat-input-actions">
                <button type="submit" disabled={isLoading || !query.trim()} className="send-btn" title="Kirim">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                    <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                {isLoading && (
                  <button type="button" onClick={handleStop} className="stop-btn" title="Hentikan">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                      <rect x="6" y="6" width="12" height="12" fill="currentColor" rx="2"/>
                    </svg>
                  </button>
                )}
              </div>
            </form>
          </div>
        )}

        {activeView === "preview" && (
          <div className="preview-panel">
            <div className="panel-header">
              <h2>Live Preview</h2>
              <div className="panel-header-right">
                {previewFiles.length > 0 && (
                  <select
                    className="preview-file-select"
                    value={selectedPreviewFile}
                    onChange={(e) => setSelectedPreviewFile(e.target.value)}
                  >
                    {previewFiles.map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                )}
                <button className="refresh-btn" onClick={refreshPreview} title="Refresh Preview">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="23 4 23 10 17 10"/>
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                  </svg>
                </button>
              </div>
            </div>
            <div className="preview-content">
              {previewFiles.length > 0 && selectedPreviewFile ? (
                <div className="preview-frame">
                  <div className="browser-toolbar">
                    <div className="browser-dots">
                      <span className="dot red" />
                      <span className="dot yellow" />
                      <span className="dot green" />
                    </div>
                    <div className="browser-url-bar">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/></svg>
                      <span>{selectedPreviewFile}</span>
                    </div>
                  </div>
                  <iframe
                    ref={previewIframeRef}
                    src={`${BACKEND_URL}/api/preview/${selectedPreviewFile}`}
                    title="Live Preview"
                    className="preview-iframe"
                    sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                  />
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                      <line x1="8" y1="21" x2="16" y2="21"/>
                      <line x1="12" y1="17" x2="12" y2="21"/>
                    </svg>
                  </div>
                  <h3>Belum Ada Preview</h3>
                  <p>Preview website yang dibuat AI akan tampil di sini secara langsung.</p>
                  <p className="empty-hint">Minta AI membuat website HTML untuk melihat preview-nya di sini.</p>
                  <button className="empty-action-btn" onClick={() => { setActiveView("chat"); setQuery("Buatkan website landing page modern"); }}>
                    Buat Website Sekarang
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {activeView === "editor" && (
          <div className="editor-panel">
            <div className="editor-layout">
              <div className="editor-sidebar">
                <div className="editor-sidebar-header">
                  <span className="editor-sidebar-title">File Project</span>
                  <button className="refresh-btn-sm" onClick={fetchProjectFiles} title="Refresh">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="23 4 23 10 17 10"/>
                      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                    </svg>
                  </button>
                </div>
                <div className="editor-file-tree">
                  {projectFiles.length > 0 ? (
                    projectFiles.map((file, index) => (
                      <button
                        key={index}
                        className={`editor-file-item ${editorContent?.file === file.name ? "active" : ""}`}
                        onClick={() => fetchEditorFileContent(file.name)}
                        title={file.name}
                      >
                        <span className="editor-file-icon">{getFileExtIcon(file.name)}</span>
                        <div className="editor-file-info">
                          <span className="editor-file-name">{file.name}</span>
                          <span className="editor-file-size">{formatFileSize(file.size)}</span>
                        </div>
                      </button>
                    ))
                  ) : (
                    <div className="editor-empty-tree">
                      <p>Belum ada file.</p>
                      <p className="editor-empty-hint">Minta AI untuk membuat project.</p>
                    </div>
                  )}
                </div>
              </div>
              <div className="editor-main">
                {editorContent ? (
                  <>
                    <div className="editor-header">
                      <div className="editor-header-left">
                        <span className="editor-file-badge">{getFileExtIcon(editorContent.file)}</span>
                        <span className="editor-filename">{editorContent.file}</span>
                        <span className="editor-filesize">{formatFileSize(editorContent.size)}</span>
                        {editorModified && <span className="editor-modified-dot">*</span>}
                      </div>
                      <div className="editor-header-right">
                        {saveStatus === "saved" && (
                          <span className="save-status success">Tersimpan ✓</span>
                        )}
                        {saveStatus === "error" && (
                          <span className="save-status error">Gagal menyimpan</span>
                        )}
                        <button
                          className={`editor-save-btn ${editorModified ? "active" : ""}`}
                          onClick={handleSaveFile}
                          disabled={!editorModified || isSaving}
                          title="Simpan (Ctrl+S)"
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                            <polyline points="17 21 17 13 7 13 7 21"/>
                            <polyline points="7 3 7 8 15 8"/>
                          </svg>
                          {isSaving ? "Menyimpan..." : "Simpan"}
                        </button>
                      </div>
                    </div>
                    <div className="editor-code-area">
                      <div className="editor-line-numbers">
                        {getLineNumbers(editorContent.content)}
                      </div>
                      <textarea
                        className="editor-textarea"
                        value={editorContent.content}
                        onChange={(e) => {
                          setEditorContent(prev => ({ ...prev, content: e.target.value }));
                          setEditorModified(true);
                        }}
                        onKeyDown={handleEditorKeyDown}
                        spellCheck={false}
                        wrap="off"
                      />
                    </div>
                  </>
                ) : (
                  <div className="empty-state">
                    <div className="empty-icon">
                      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="16 18 22 12 16 6"/>
                        <polyline points="8 6 2 12 8 18"/>
                      </svg>
                    </div>
                    <h3>Editor Kode</h3>
                    <p>Pilih file dari panel kiri untuk mulai mengedit. Perubahan bisa disimpan langsung ke project.</p>
                    <p className="empty-hint">Gunakan Ctrl+S untuk menyimpan dengan cepat.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeView === "files" && (
          <div className="files-panel">
            <div className="panel-header">
              <h2>File Project</h2>
              <div className="panel-header-right">
                <span className="panel-badge">{projectFiles.length} file</span>
                <button className="refresh-btn" onClick={fetchProjectFiles} title="Refresh">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="23 4 23 10 17 10"/>
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                  </svg>
                </button>
                <button className="download-zip-btn" onClick={handleDownloadZip} title="Unduh Project sebagai .ZIP">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  <span>Unduh .ZIP</span>
                </button>
              </div>
            </div>
            <div className="files-layout">
              <div className="files-list">
                {projectFiles.length > 0 ? (
                  projectFiles.map((file, index) => (
                    <button
                      key={index}
                      className={`file-item ${selectedFileContent?.file === file.name ? "active" : ""}`}
                      onClick={() => fetchFileContent(file.name)}
                    >
                      <div className="file-icon" style={{ background: getFileIcon(file.name) }} />
                      <div className="file-info">
                        <span className="file-name">{file.name}</span>
                        <span className="file-size">{formatFileSize(file.size)}</span>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="empty-state small">
                    <p>Belum ada file project.</p>
                    <p className="empty-hint">Minta AI membuat sesuatu untuk melihat file di sini.</p>
                  </div>
                )}
              </div>
              <div className="file-viewer">
                {selectedFileContent ? (
                  <div className="file-viewer-content">
                    <div className="file-viewer-header">
                      <div className="file-viewer-header-left">
                        <span className="file-viewer-icon">{getFileExtIcon(selectedFileContent.file)}</span>
                        <span className="file-viewer-name">{selectedFileContent.file}</span>
                      </div>
                      <div className="file-viewer-header-right">
                        <span className="file-viewer-size">{formatFileSize(selectedFileContent.size)}</span>
                        <button
                          className="file-download-btn"
                          onClick={() => handleDownloadFile(selectedFileContent.file)}
                          title="Unduh file ini"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/>
                            <line x1="12" y1="15" x2="12" y2="3"/>
                          </svg>
                        </button>
                        <button
                          className="file-edit-btn"
                          onClick={() => {
                            setEditorContent({ ...selectedFileContent });
                            setEditorModified(false);
                            setActiveView("editor");
                          }}
                          title="Edit di Editor"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                    <pre className="file-viewer-code">{selectedFileContent.content}</pre>
                  </div>
                ) : (
                  <div className="empty-state">
                    <div className="empty-icon">
                      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                      </svg>
                    </div>
                    <p>Pilih file untuk melihat isinya</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeView === "browser" && (
          <div className="browser-panel">
            <div className="panel-header">
              <h2>Browser View</h2>
              <button className="refresh-btn" onClick={fetchScreenshot} title="Refresh">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="23 4 23 10 17 10"/>
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                </svg>
              </button>
            </div>
            <div className="browser-content">
              {responseData?.screenshot ? (
                <div className="browser-frame">
                  <div className="browser-toolbar">
                    <div className="browser-dots">
                      <span className="dot red" />
                      <span className="dot yellow" />
                      <span className="dot green" />
                    </div>
                    <div className="browser-url-bar">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/></svg>
                      <span>agent-browser://preview</span>
                    </div>
                  </div>
                  <img
                    src={responseData.screenshot}
                    alt="Browser Screenshot"
                    className="browser-screenshot"
                    key={responseData.screenshotTimestamp || "default"}
                  />
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/>
                      <line x1="2" y1="12" x2="22" y2="12"/>
                      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                    </svg>
                  </div>
                  <h3>Browser Preview</h3>
                  <p>Tampilan browser akan muncul di sini saat AI agent membuka halaman web.</p>
                  <p className="empty-hint">Minta AI untuk membuka website untuk melihat preview-nya.</p>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      <div className="mobile-bottom-nav">
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`bottom-nav-item ${activeView === item.id ? "active" : ""}`}
            onClick={() => setActiveView(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="bottom-nav-label">{item.label}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="toast-error">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          <span>{error}</span>
          <button onClick={() => setError(null)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      )}
    </div>
  );
}

export default App;
