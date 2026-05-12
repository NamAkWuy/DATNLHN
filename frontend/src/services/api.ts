import axios from 'axios'
import type {
  ApiResponse,
  LoginResponse,
  User,
  Department,
  Employee,
  AttendanceLog,
  LeaveRequest,
  RFIDCard,
  ReportSummary,
  AttendanceReport,
  PaginatedResponse,
  Notification,
} from '../types'

// Dùng đường dẫn tương đối — Vite dev proxy (vite.config.ts) sẽ chuyển tiếp
// /api → http://localhost:8000. Tránh CORS preflight và IPv4/IPv6 mismatch.
const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Interceptor cho request: gắn token xác thực vào header
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Interceptor cho response: xử lý lỗi tập trung
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLoginEndpoint = error.config?.url?.includes('/auth/login')
    if (error.response?.status === 401 && !isLoginEndpoint) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    // Lấy message tiếng Việt từ backend thay vì message mặc định của axios
    const data = error.response?.data
    const detail = data?.detail
    if (typeof detail === 'string') {
      return Promise.reject(new Error(detail))
    }
    // Pydantic validation error: detail là array các object {loc, msg, type}
    // → ghép message của từng lỗi để user biết field nào sai.
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((e: { loc?: (string | number)[]; msg?: string }) => {
          const field = e.loc?.slice(-1)[0]
          return field ? `${field}: ${e.msg}` : e.msg
        })
        .filter(Boolean)
        .join('; ')
      return Promise.reject(new Error(msgs || 'Dữ liệu không hợp lệ.'))
    }
    // Backend trả về dạng {success: false, message: "..."} (success_response)
    if (typeof data?.message === 'string') {
      return Promise.reject(new Error(data.message))
    }
    if (!error.response) {
      return Promise.reject(new Error('Không thể kết nối đến máy chủ. Vui lòng kiểm tra lại mạng.'))
    }
    // 500 không có detail rõ ràng — kèm status code để debug
    const status = error.response?.status
    return Promise.reject(new Error(
      `Đã xảy ra lỗi (HTTP ${status ?? '?'}). Vui lòng kiểm tra log backend.`
    ))
  }
)

// ─── Xác thực ───────────────────────────────────────────────────────────────
export const authApi = {
  login: async (username: string, password: string) => {
    const res = await api.post<ApiResponse<LoginResponse>>('/auth/login', {
      username,
      password,
    })
    return res.data
  },
  logout: async () => {
    const res = await api.post<ApiResponse<null>>('/auth/logout')
    return res.data
  },
  getMe: async () => {
    const res = await api.get<ApiResponse<User>>('/auth/me')
    return res.data
  },
}

// ─── Phòng ban ──────────────────────────────────────────────────────────────
export const departmentApi = {
  getAll: async () => {
    const res = await api.get<ApiResponse<Department[]>>('/departments')
    return res.data
  },
  create: async (data: { name: string }) => {
    const res = await api.post<ApiResponse<Department>>('/departments', data)
    return res.data
  },
  update: async (id: number, data: { name: string }) => {
    const res = await api.put<ApiResponse<Department>>(`/departments/${id}`, data)
    return res.data
  },
  delete: async (id: number) => {
    const res = await api.delete<ApiResponse<null>>(`/departments/${id}`)
    return res.data
  },
}

// ─── Nhân viên ──────────────────────────────────────────────────────────────
export interface EmployeeParams {
  search?: string
  department_id?: number
  status?: string
  page?: number
  page_size?: number
}

export const employeeApi = {
  getAll: async (params?: EmployeeParams) => {
    const res = await api.get<ApiResponse<PaginatedResponse<Employee>>>('/employees', { params })
    return res.data
  },
  getById: async (id: number) => {
    const res = await api.get<ApiResponse<Employee>>(`/employees/${id}`)
    return res.data
  },
  create: async (data: Partial<Employee> & { password?: string }) => {
    const res = await api.post<ApiResponse<Employee & { username: string; temp_password?: string }>>('/employees', data)
    return res.data
  },
  update: async (id: number, data: Partial<Employee>) => {
    const res = await api.put<ApiResponse<Employee>>(`/employees/${id}`, data)
    return res.data
  },
  delete: async (id: number) => {
    const res = await api.delete<ApiResponse<null>>(`/employees/${id}`)
    return res.data
  },
  uploadAvatar: async (id: number, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post<ApiResponse<{ avatar_url: string }>>(`/employees/${id}/avatar`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },
}

// ─── Khuôn mặt ──────────────────────────────────────────────────────────────
export const faceApi = {
  // image_base64 = ảnh chính (template primary trên backend).
  // extra_images = các pose phụ (góc khác / có-không kính) — backend lưu mỗi
  // ảnh thành một template trong gallery, giúp nhận diện ổn định khi user
  // thay đổi trạng thái nhỏ (đeo/cởi kính, nghiêng nhẹ).
  register: async (
    employee_id: number,
    image_base64: string,
    extra_images?: string[],
  ) => {
    const res = await api.post<ApiResponse<{ extras_added?: number; extras_failed?: number }>>(
      `/face/register/${employee_id}`,
      {
        image_base64,
        ...(extra_images && extra_images.length > 0 ? { extra_images } : {}),
      },
      {
        // Backend phải extract embedding cho từng ảnh (~0.5–1s/ảnh với MTCNN+ArcFace)
        timeout: 10000 + 3000 * (extra_images?.length ?? 0),
      },
    )
    return res.data
  },
  delete: async (employee_id: number) => {
    const res = await api.delete<ApiResponse<null>>(`/face/${employee_id}`)
    return res.data
  },
  check: async (employee_id: number) => {
    const res = await api.get<ApiResponse<{ has_face: boolean; registered_at?: string }>>(`/face/${employee_id}`)
    return res.data
  },
}

// ─── Thẻ RFID ───────────────────────────────────────────────────────────────
export const rfidApi = {
  getAll: async () => {
    const res = await api.get<ApiResponse<RFIDCard[]>>('/rfid')
    return res.data
  },
  create: async (data: { uid: string; employee_id?: number }) => {
    const res = await api.post<ApiResponse<RFIDCard>>('/rfid', data)
    return res.data
  },
  assign: async (id: number, employee_id: number) => {
    const res = await api.put<ApiResponse<RFIDCard>>(`/rfid/${id}/assign`, { employee_id })
    return res.data
  },
  updateStatus: async (id: number, status: 'active' | 'disabled') => {
    const res = await api.put<ApiResponse<RFIDCard>>(`/rfid/${id}/status`, { status })
    return res.data
  },
  delete: async (id: number) => {
    const res = await api.delete<ApiResponse<null>>(`/rfid/${id}`)
    return res.data
  },
}

// ─── Chấm công ──────────────────────────────────────────────────────────────
export interface AttendanceParams {
  date?: string
  employee_id?: number
  search?: string
  page?: number
  page_size?: number
  month?: number
  year?: number
}

export const attendanceApi = {
  getLogs: async (params?: AttendanceParams) => {
    const res = await api.get<ApiResponse<PaginatedResponse<AttendanceLog>>>('/attendance', { params })
    return res.data
  },
  getMyAttendance: async (params?: AttendanceParams) => {
    const res = await api.get<ApiResponse<AttendanceLog[]>>('/attendance/my', { params })
    return res.data
  },
  createManual: async (data: {
    employee_id: number
    date: string
    check_in: string
    check_out?: string
    note?: string
  }) => {
    const res = await api.post<ApiResponse<AttendanceLog>>('/attendance/manual', data)
    return res.data
  },
  update: async (id: number, data: Partial<AttendanceLog>) => {
    const res = await api.put<ApiResponse<AttendanceLog>>(`/attendance/${id}`, data)
    return res.data
  },
  delete: async (id: number) => {
    const res = await api.delete<ApiResponse<null>>(`/attendance/${id}`)
    return res.data
  },
}

// ─── Đơn từ ─────────────────────────────────────────────────────────────────
export interface LeaveParams {
  status?: string
  page?: number
  page_size?: number
}

export const leaveApi = {
  getAll: async (params?: LeaveParams) => {
    const res = await api.get<ApiResponse<PaginatedResponse<LeaveRequest>>>('/requests', { params })
    return res.data
  },
  getMyRequests: async (params?: LeaveParams) => {
    const res = await api.get<ApiResponse<PaginatedResponse<LeaveRequest>>>('/requests/my', { params })
    return res.data
  },
  create: async (data: {
    type: LeaveRequest['type']
    start_datetime: string
    end_datetime: string
    reason: string
  }) => {
    const res = await api.post<ApiResponse<LeaveRequest>>('/requests', data)
    return res.data
  },
  update: async (id: number, data: Partial<LeaveRequest>) => {
    const res = await api.put<ApiResponse<LeaveRequest>>(`/requests/${id}`, data)
    return res.data
  },
  cancel: async (id: number) => {
    const res = await api.delete<ApiResponse<LeaveRequest>>(`/requests/${id}`)
    return res.data
  },
  approve: async (id: number) => {
    const res = await api.put<ApiResponse<LeaveRequest>>(`/requests/${id}/approve`)
    return res.data
  },
  reject: async (id: number, reject_reason: string) => {
    const res = await api.put<ApiResponse<LeaveRequest>>(`/requests/${id}/reject`, { reject_reason })
    return res.data
  },
}

// ─── Báo cáo ────────────────────────────────────────────────────────────────
export const reportApi = {
  getSummary: async () => {
    const res = await api.get<ApiResponse<ReportSummary>>('/reports/summary')
    return res.data
  },
  getAttendanceReport: async (month: number, year: number) => {
    const res = await api.get<ApiResponse<{
      month: number
      year: number
      records: AttendanceReport[]
      total_employees: number
    }>>('/reports/attendance', {
      params: { month, year },
    })
    return res.data
  },
  exportExcel: async (month: number, year: number) => {
    const res = await api.get('/reports/export/excel', {
      params: { month, year },
      responseType: 'blob',
    })
    return res.data
  },
  exportPDF: async (month: number, year: number) => {
    const res = await api.get('/reports/export/pdf', {
      params: { month, year },
      responseType: 'blob',
    })
    return res.data
  },
  getChartData: async () => {
    const res = await api.get<ApiResponse<{ date: string; present: number; absent: number }[]>>(
      '/reports/chart/weekly'
    )
    return res.data
  },
}

// ─── Thông báo ──────────────────────────────────────────────────────────────
export interface NotificationParams {
  unread_only?: boolean
  page?: number
  page_size?: number
}

export const notificationApi = {
  getAll: async (params?: NotificationParams) => {
    const res = await api.get<ApiResponse<PaginatedResponse<Notification>>>('/notifications', {
      params,
    })
    return res.data
  },
  getUnreadCount: async () => {
    const res = await api.get<ApiResponse<{ unread: number }>>('/notifications/unread-count')
    return res.data
  },
  markRead: async (id: number) => {
    const res = await api.put<ApiResponse<Notification>>(`/notifications/${id}/read`)
    return res.data
  },
  markAllRead: async () => {
    const res = await api.put<ApiResponse<{ updated: number }>>('/notifications/read-all')
    return res.data
  },
  delete: async (id: number) => {
    const res = await api.delete<ApiResponse<null>>(`/notifications/${id}`)
    return res.data
  },
  clearAll: async () => {
    const res = await api.delete<ApiResponse<{ deleted: number }>>('/notifications')
    return res.data
  },
}

export default api
