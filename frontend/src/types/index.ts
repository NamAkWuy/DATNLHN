export interface User {
  id: number;
  username: string;
  role: 'admin' | 'employee';
  employee_id: number;
  full_name: string;
}

export interface Department {
  id: number;
  name: string;
  employee_count: number;
  created_at?: string;
}

export interface Employee {
  id: number;
  employee_code: string;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  department_id: number;
  department?: { id: number; name: string };
  status: 'active' | 'inactive';
  avatar_url?: string;
  has_face: boolean;
  face_template_count?: number;   // số template trong gallery (1 primary + N phụ)
  has_rfid: boolean;
  created_at: string;
  updated_at?: string;
  username?: string;
  role?: 'admin' | 'employee';
}

export interface AttendanceLog {
  id: number;
  employee_id: number;
  employee?: { id: number; full_name: string; employee_code: string };
  check_in: string;
  check_out?: string;
  note?: string;
  date: string;
  work_hours?: number;
  created_at?: string;
}

export interface LeaveRequest {
  id: number;
  employee_id: number;
  employee?: { id: number; full_name: string; employee_code: string };
  type: 'nghi_phep' | 'di_muon' | 've_som';
  start_datetime: string;
  end_datetime: string;
  reason: string;
  status: 'cho_duyet' | 'da_duyet' | 'tu_choi' | 'da_huy';
  reject_reason?: string;
  reviewed_by?: number;
  reviewer?: { id: number; username: string };
  reviewed_at?: string;
  created_at: string;
  updated_at?: string;
}

export interface RFIDCard {
  id: number;
  uid: string;
  employee_id?: number;
  employee?: { id: number; full_name: string; employee_code: string };
  status: 'active' | 'disabled';
  assigned_at?: string;
  created_at?: string;
}

export interface ReportSummary {
  total_employees: number;
  present_today: number;
  absent_today: number;
  pending_requests: number;
  late_this_month: number;
}

export interface AttendanceReport {
  employee_id: number;
  employee_code: string;
  full_name: string;
  department: string;
  total_days_worked: number;
  total_work_hours: number;
  late_count: number;
  early_leave_count: number;
  absent_count: number;
  leave_days: number;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Notification {
  id: number;
  type: string;
  title: string;
  message: string;
  link?: string | null;
  is_read: boolean;
  read_at?: string | null;
  created_at: string;
}
