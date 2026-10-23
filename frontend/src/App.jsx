import React, { useEffect, useState } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:8000';

export default function App() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch tasks from FastAPI Backend
  const fetchTasks = async () => {
    try {
      const res = await axios.get(`${API_URL}/tasks`);
      setTasks(res.data);
    } catch (err) {
      console.error('Error fetching tasks:', err);
    } finally {
      setLoading(false);
    }
  };

  // Poll for new tasks every 3 seconds for real-time synchronization
  useEffect(() => {
    fetchTasks();
    const interval = setInterval(() => {
      fetchTasks();
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  // Handle Drag Start (store the task ID)
  const handleDragStart = (e, taskId) => {
    e.dataTransfer.setData('taskId', String(taskId));
    e.dataTransfer.effectAllowed = 'move';
  };

  // Handle Drop on a Column (update task status via PATCH)
  const handleDrop = async (e, newStatus) => {
    e.preventDefault();
    const taskId = e.dataTransfer.getData('taskId');
    if (!taskId) return;

    try {
      await axios.patch(`${API_URL}/tasks/${taskId}`, { status: newStatus });
      fetchTasks(); // Refresh immediately after update
    } catch (err) {
      console.error('Error updating task status:', err);
    }
  };

  const columns = ['Pending', 'In Progress', 'Completed'];

  return (
    <div style={{ padding: '30px', maxWidth: '1200px', margin: '0 auto', fontFamily: 'sans-serif' }}>
      <header style={{ marginBottom: '30px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, color: '#1a1a1a' }}>Task Management Dashboard</h1>
          <p style={{ color: '#666', marginTop: '5px' }}>
            Real-time synchronization with Telegram Bot & Local AI Worker
          </p>
        </div>

        <button
          onClick={fetchTasks}
          style={{
            padding: '10px 18px',
            backgroundColor: '#0070f3',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: 'bold',
          }}
        >
          🔄 Refresh
        </button>
      </header>

      {loading ? (
        <p>Loading tasks...</p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
          {columns.map((status) => {
            const columnTasks = tasks.filter((t) => t.status === status);
            return (
              <div
                key={status}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => handleDrop(e, status)}
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: '8px',
                  padding: '20px',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                  minHeight: '400px',
                  border: '2px dashed #eaeaea',
                }}
              >
                <h3
                  style={{
                    marginTop: 0,
                    borderBottom: '2px solid #eaeaea',
                    paddingBottom: '10px',
                    display: 'flex',
                    justifyContent: 'space-between',
                  }}
                >
                  <span>{status}</span>
                  <span style={{ fontSize: '14px', color: '#888' }}>{columnTasks.length}</span>
                </h3>

                {columnTasks.length === 0 ? (
                  <p style={{ color: '#aaa', fontStyle: 'italic', fontSize: '14px', textAlign: 'center', marginTop: '40px' }}>
                    Drop tasks here
                  </p>
                ) : (
                  columnTasks.map((task) => (
                    <div
                      key={task.id}
                      draggable
                      onDragStart={(e) => handleDragStart(e, task.id)}
                      style={{
                        backgroundColor: '#f9f9fb',
                        border: '1px solid #e1e4e8',
                        borderRadius: '6px',
                        padding: '15px',
                        marginBottom: '12px',
                        cursor: 'grab',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                      }}
                    >
                      <h4 style={{ margin: '0 0 8px 0', fontSize: '16px', color: '#333' }}>{task.title}</h4>
                      {task.description && (
                        <p style={{ margin: '0 0 10px 0', fontSize: '14px', color: '#555' }}>{task.description}</p>
                      )}
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          fontSize: '12px',
                          color: '#888',
                        }}
                      >
                        <span
                          style={{
                            padding: '2px 8px',
                            borderRadius: '4px',
                            backgroundColor: task.source?.includes('voice') ? '#e6f7ff' : '#f6ffed',
                            color: task.source?.includes('voice') ? '#1890ff' : '#52c41a',
                            fontWeight: '500',
                          }}
                        >
                          {task.source}
                        </span>
                        <span>{new Date(task.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}