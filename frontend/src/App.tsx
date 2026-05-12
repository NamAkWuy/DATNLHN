import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'

// Trang chung
import Login from './pages/Login'
import NotFound from './pages/NotFound'

// Trang dành cho admin
import Dashboard from './pages/admin/Dashboard'
import Employees from './pages/admin/Employees'
import Departments from './pages/admin/Departments'
import FaceManagement from './pages/admin/FaceManagement'
import RFIDManagement from './pages/admin/RFIDManagement'
import AttendanceManagement from './pages/admin/AttendanceManagement'
import LeaveApproval from './pages/admin/LeaveApproval'
import Reports from './pages/admin/Reports'

// Trang dành cho nhân viên
import MyDashboard from './pages/employee/MyDashboard'
import MyAttendance from './pages/employee/MyAttendance'
import MyRequests from './pages/employee/MyRequests'
import Profile from './pages/employee/Profile'

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Trang công khai */}
          <Route path="/login" element={<Login />} />

          {/* Trang chủ — chuyển hướng về login */}
          <Route path="/" element={<Navigate to="/login" replace />} />

          {/* Các route dành cho admin */}
          <Route
            path="/admin"
            element={
              <ProtectedRoute role="admin">
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="employees" element={<Employees />} />
            <Route path="departments" element={<Departments />} />
            <Route path="face" element={<FaceManagement />} />
            <Route path="rfid" element={<RFIDManagement />} />
            <Route path="attendance" element={<AttendanceManagement />} />
            <Route path="leave" element={<LeaveApproval />} />
            <Route path="reports" element={<Reports />} />
          </Route>

          {/* Các route dành cho nhân viên */}
          <Route
            path="/my"
            element={
              <ProtectedRoute role="employee">
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/my/dashboard" replace />} />
            <Route path="dashboard" element={<MyDashboard />} />
            <Route path="attendance" element={<MyAttendance />} />
            <Route path="requests" element={<MyRequests />} />
            <Route path="profile" element={<Profile />} />
          </Route>

          {/* Trang không tìm thấy (404) */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
