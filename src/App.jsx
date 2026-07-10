import { useState, useEffect } from 'react'
import './index.css'

function App() {
  const [tasks, setTasks] = useState(() => {
    const saved = localStorage.getItem('tasks')
    if (saved) {
      try {
        return JSON.parse(saved)
      } catch (e) {
        console.error(e)
      }
    }
    return [
      {
        id: '1',
        title: 'Diseñar la interfaz de usuario',
        description: 'Crear un diseño moderno con Glassmorphism, gradientes suaves y micro-interacciones.',
        priority: 'high',
        status: 'completed',
        dueDate: '2026-07-15'
      },
      {
        id: '2',
        title: 'Implementar CRUD en React',
        description: 'Asegurar que las operaciones de creación, lectura, actualización y eliminación funcionen correctamente en el estado local.',
        priority: 'medium',
        status: 'in_progress',
        dueDate: '2026-07-20'
      },
      {
        id: '3',
        title: 'Optimizar estilos CSS',
        description: 'Usar variables CSS HSL, fuentes de Google Fonts, y transiciones fluidas.',
        priority: 'low',
        status: 'todo',
        dueDate: '2026-07-25'
      }
    ]
  })

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState('medium')
  const [status, setStatus] = useState('todo')
  const [dueDate, setDueDate] = useState('')
  
  const [editingId, setEditingId] = useState(null)
  const [search, setSearch] = useState('')
  const [filterPriority, setFilterPriority] = useState('all')
  const [filterStatus, setFilterStatus] = useState('all')

  useEffect(() => {
    localStorage.setItem('tasks', JSON.stringify(tasks))
  }, [tasks])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!title.trim()) return

    if (editingId) {
      setTasks(tasks.map(task => 
        task.id === editingId 
          ? { ...task, title, description, priority, status, dueDate }
          : task
      ))
      setEditingId(null)
    } else {
      const newTask = {
        id: Date.now().toString(),
        title,
        description,
        priority,
        status,
        dueDate: dueDate || new Date().toISOString().split('T')[0]
      }
      setTasks([newTask, ...tasks])
    }

    // Reset Form
    setTitle('')
    setDescription('')
    setPriority('medium')
    setStatus('todo')
    setDueDate('')
  }

  const handleEdit = (task) => {
    setEditingId(task.id)
    setTitle(task.title)
    setDescription(task.description)
    setPriority(task.priority)
    setStatus(task.status)
    setDueDate(task.dueDate)
  }

  const handleDelete = (id) => {
    if (confirm('¿Estás seguro de que deseas eliminar esta tarea?')) {
      setTasks(tasks.filter(task => task.id !== id))
      if (editingId === id) {
        setEditingId(null)
        setTitle('')
        setDescription('')
        setPriority('medium')
        setStatus('todo')
        setDueDate('')
      }
    }
  }

  const toggleStatus = (id) => {
    setTasks(tasks.map(task => {
      if (task.id === id) {
        const nextStatus = task.status === 'completed' ? 'todo' : 'completed'
        return { ...task, status: nextStatus }
      }
      return task
    }))
  }

  const cancelEdit = () => {
    setEditingId(null)
    setTitle('')
    setDescription('')
    setPriority('medium')
    setStatus('todo')
    setDueDate('')
  }

  // Filtering and Searching
  const filteredTasks = tasks.filter(task => {
    const matchesSearch = task.title.toLowerCase().includes(search.toLowerCase()) || 
                          task.description.toLowerCase().includes(search.toLowerCase())
    const matchesPriority = filterPriority === 'all' || task.priority === filterPriority
    const matchesStatus = filterStatus === 'all' || task.status === filterStatus
    return matchesSearch && matchesPriority && matchesStatus
  })

  // Stats
  const totalCount = tasks.length
  const completedCount = tasks.filter(t => t.status === 'completed').length
  const inProgressCount = tasks.filter(t => t.status === 'in_progress').length
  const todoCount = tasks.filter(t => t.status === 'todo').length

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-logo">
          <svg className="logo-icon" viewBox="0 0 24 24" width="32" height="32">
            <path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-9 14l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
          </svg>
          <h1>TaskFlow</h1>
        </div>
        <p className="header-subtitle">Gestiona tus proyectos y tareas con elegancia y simplicidad.</p>
      </header>

      {/* Metrics Section */}
      <section className="metrics-grid">
        <div className="metric-card total">
          <span className="metric-title">Total</span>
          <span className="metric-value">{totalCount}</span>
        </div>
        <div className="metric-card todo">
          <span className="metric-title">Pendientes</span>
          <span className="metric-value">{todoCount}</span>
        </div>
        <div className="metric-card in-progress">
          <span className="metric-title">En Progreso</span>
          <span className="metric-value">{inProgressCount}</span>
        </div>
        <div className="metric-card completed">
          <span className="metric-title">Completadas</span>
          <span className="metric-value">{completedCount}</span>
        </div>
      </section>

      <main className="main-content">
        {/* Form Container */}
        <section className="form-section">
          <div className="glass-card">
            <h2>{editingId ? 'Editar Tarea' : 'Nueva Tarea'}</h2>
            <form onSubmit={handleSubmit} className="task-form">
              <div className="form-group">
                <label htmlFor="title">Título</label>
                <input
                  type="text"
                  id="title"
                  placeholder="Ej. Comprar materiales de oficina"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="description">Descripción</label>
                <textarea
                  id="description"
                  placeholder="Detalles sobre la tarea..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows="3"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="priority">Prioridad</label>
                  <select
                    id="priority"
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                  >
                    <option value="low">Baja 🟢</option>
                    <option value="medium">Media 🟡</option>
                    <option value="high">Alta 🔴</option>
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="status">Estado</label>
                  <select
                    id="status"
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    <option value="todo">Pendiente</option>
                    <option value="in_progress">En Progreso</option>
                    <option value="completed">Completada</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="dueDate">Fecha de vencimiento</label>
                <input
                  type="date"
                  id="dueDate"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                />
              </div>

              <div className="form-actions">
                <button type="submit" className="btn btn-primary">
                  {editingId ? 'Guardar Cambios' : 'Crear Tarea'}
                </button>
                {editingId && (
                  <button type="button" onClick={cancelEdit} className="btn btn-secondary">
                    Cancelar
                  </button>
                )}
              </div>
            </form>
          </div>
        </section>

        {/* Task List Section */}
        <section className="list-section">
          {/* Controls Bar */}
          <div className="controls-bar">
            <div className="search-box">
              <svg className="search-icon" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
              </svg>
              <input
                type="text"
                placeholder="Buscar tareas..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            
            <div className="filters-box">
              <select
                value={filterPriority}
                onChange={(e) => setFilterPriority(e.target.value)}
                aria-label="Filtrar por prioridad"
              >
                <option value="all">Todas las prioridades</option>
                <option value="low">Prioridad Baja</option>
                <option value="medium">Prioridad Media</option>
                <option value="high">Prioridad Alta</option>
              </select>

              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                aria-label="Filtrar por estado"
              >
                <option value="all">Todos los estados</option>
                <option value="todo">Pendientes</option>
                <option value="in_progress">En Progreso</option>
                <option value="completed">Completadas</option>
              </select>
            </div>
          </div>

          {/* Cards Grid */}
          <div className="tasks-grid">
            {filteredTasks.length > 0 ? (
              filteredTasks.map((task) => (
                <div key={task.id} className={`task-card ${task.status} ${task.priority}-priority`}>
                  <div className="task-card-header">
                    <button
                      className="checkbox-btn"
                      onClick={() => toggleStatus(task.id)}
                      title={task.status === 'completed' ? 'Marcar como pendiente' : 'Marcar como completada'}
                    >
                      {task.status === 'completed' ? (
                        <svg viewBox="0 0 24 24" width="22" height="22" className="checked-icon">
                          <path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" width="22" height="22" className="unchecked-icon">
                          <path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"/>
                        </svg>
                      )}
                    </button>
                    <span className={`badge badge-priority badge-${task.priority}`}>
                      {task.priority === 'high' ? 'Alta' : task.priority === 'medium' ? 'Media' : 'Baja'}
                    </span>
                    <span className={`badge badge-status badge-${task.status}`}>
                      {task.status === 'completed' ? 'Completada' : task.status === 'in_progress' ? 'En Progreso' : 'Pendiente'}
                    </span>
                  </div>

                  <h3 className="task-title">{task.title}</h3>
                  <p className="task-desc">{task.description}</p>

                  <div className="task-card-footer">
                    <span className="due-date">
                      <svg viewBox="0 0 24 24" width="14" height="14">
                        <path fill="currentColor" d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2z"/>
                      </svg>
                      {task.dueDate}
                    </span>
                    <div className="card-actions">
                      <button onClick={() => handleEdit(task)} className="action-btn edit-btn" title="Editar Tarea">
                        <svg viewBox="0 0 24 24" width="16" height="16">
                          <path fill="currentColor" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                        </svg>
                      </button>
                      <button onClick={() => handleDelete(task.id)} className="action-btn delete-btn" title="Eliminar Tarea">
                        <svg viewBox="0 0 24 24" width="16" height="16">
                          <path fill="currentColor" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="no-tasks">
                <svg viewBox="0 0 24 24" width="48" height="48" className="empty-icon">
                  <path fill="currentColor" d="M22 16V4c0-1.1-.9-2-2-2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2zm-11-4l2.03 2.71L16 11l4 5H8l3-4zM2 6v14c0 1.1.9 2 2 2h14v-2H4V6H2z"/>
                </svg>
                <p>No se encontraron tareas. ¡Crea una nueva para empezar!</p>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
