import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Clock, Calendar, FileText, CheckCircle, AlertCircle, Plus } from 'lucide-react'
import { attendanceApi, leaveApi } from '../../services/api'
import { useAuth } from '../../hooks/useAuth'
import { useAttendanceTimer } from '../../hooks/useAttendanceTimer'
import { format } from 'date-fns'
import { vi } from 'date-fns/locale'
import Modal from '../../components/Modal'
import LoadingSpinner from '../../components/LoadingSpinner'
import type { AttendanceLog } from '../../types'

const MyDashboard: React.FC = () => {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { formattedTime, formattedDate } = useAttendanceTimer()
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const [leaveForm, setLeaveForm] = useState({
    type: 'nghi_phep' as 'nghi_phep' | 'di_muon' | 've_som',
    start_datetime: '',
    end_datetime: '',
    reason: '',
  })
  const [leaveErrors, setLeaveErrors] = useState<Record<string, string>>({})

  const now = new Date()
  const currentMonth = now.getMonth() + 1
  const currentYear = now.getFullYear()

  const { data: myAttendanceData, isLoading: attendanceLoading } = useQuery({
    queryKey: ['my-attendance', currentMonth, currentYear],
    queryFn: () => attendanceApi.getMyAttendance({ month: currentMonth, year: currentYear }),
  })

  const { data: myRequestsData } = useQuery({
    queryKey: ['my-requests-pending'],
    queryFn: () => leaveApi.getMyRequests({ status: 'cho_duyet' }),
  })

  const createLeaveMutation = useMutation({
    mutationFn: leaveApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-requests'] })
      queryClient.invalidateQueries({ queryKey: ['my-requests-pending'] })
      setShowLeaveModal(false)
      setLeaveForm({ type: 'nghi_phep', start_datetime: '', end_datetime: '', reason: '' })
    },
  })

  const logs: AttendanceLog[] = myAttendanceData?.data || []
  const pendingCount = myRequestsData?.data?.total || 0

  // Bản ghi chấm công hôm nay
  const todayStr = format(now, 'yyyy-MM-dd')
  const todayLog = logs.find((l) => l.date === todayStr)

  // Thống kê tháng này
  const workedDays = logs.filter((l) => l.check_in).length
  const lateCount = logs.filter((l) => {
    if (!l.check_in) return false
    const checkInHour = new Date(l.check_in).getHours()
    const checkInMin = new Date(l.check_in).getMinutes()
    return checkInHour > 8 || (checkInHour === 8 && checkInMin > 5)
  }).length

  // 5 bản ghi gần nhất
  const recentLogs = [...logs]
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 5)

  const handleCreateLeave = () => {
    const errors: Record<string, string> = {}
    if (!leaveForm.start_datetime) errors.start_datetime = 'Bắt buộc'
    if (!leaveForm.end_datetime) errors.end_datetime = 'Bắt buộc'
    if (!leaveForm.reason.trim()) errors.reason = 'Bắt buộc'
    if (leaveForm.start_datetime && leaveForm.end_datetime && leaveForm.start_datetime >= leaveForm.end_datetime) {
      errors.end_datetime = 'Thời gian kết thúc phải sau bắt đầu'
    }
    if (Object.keys(errors).length > 0) {
      setLeaveErrors(errors)
      return
    }
    setLeaveErrors({})
    createLeaveMutation.mutate(leaveForm)
  }

  const greeting = () => {
    const h = now.getHours()
    if (h < 12) return 'Chào buổi sáng'
    if (h < 18) return 'Chào buổi chiều'
    return 'Chào buổi tối'
  }

  return (
    <div className="space-y-6">
      {/* Greeting + Time */}
      <div className="bg-gradient-to-r from-mint-600 to-teal-700 rounded-2xl p-6 text-white">
        <p className="text-mint-200 text-sm mb-1">{formattedDate}</p>
        <h1 className="text-2xl font-bold mb-1">
          {greeting()}, {user?.full_name?.split(' ').pop()}!
        </h1>
        <div className="text-4xl font-mono font-bold tracking-wider mt-3">
          {formattedTime}
        </div>
      </div>

      {/* Today Attendance Card */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Clock size={18} className="text-mint-600" />
          <h2 className="font-semibold text-gray-900">Chấm công hôm nay</h2>
          <span className="text-sm text-gray-400 ml-auto">
            {format(now, 'dd/MM/yyyy')}
          </span>
        </div>
        {attendanceLoading ? (
          <div className="flex justify-center py-4"><LoadingSpinner size="sm" /></div>
        ) : todayLog ? (
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 mb-1">Giờ vào</p>
              <p className="text-xl font-bold text-green-700">
                {todayLog.check_in ? format(new Date(todayLog.check_in), 'HH:mm') : '—'}
              </p>
            </div>
            <div className="bg-mint-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 mb-1">Giờ ra</p>
              <p className="text-xl font-bold text-mint-700">
                {todayLog.check_out ? format(new Date(todayLog.check_out), 'HH:mm') : '—'}
              </p>
            </div>
            <div className="bg-purple-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 mb-1">Số giờ</p>
              <p className="text-xl font-bold text-purple-700">
                {todayLog.work_hours != null ? `${todayLog.work_hours.toFixed(1)}h` : '—'}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 py-2 text-gray-500">
            <AlertCircle size={20} className="text-yellow-500" />
            <p className="text-sm">Chưa có dữ liệu chấm công hôm nay</p>
          </div>
        )}
      </div>

      {/* Month Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex items-center gap-3">
          <div className="w-10 h-10 bg-mint-100 rounded-xl flex items-center justify-center">
            <Calendar size={18} className="text-mint-600" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Ngày công tháng này</p>
            <p className="text-2xl font-bold text-gray-900">{workedDays}</p>
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex items-center gap-3">
          <div className="w-10 h-10 bg-yellow-100 rounded-xl flex items-center justify-center">
            <Clock size={18} className="text-yellow-600" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Số lần đi muộn</p>
            <p className="text-2xl font-bold text-gray-900">{lateCount}</p>
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex items-center gap-3">
          <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center">
            <FileText size={18} className="text-orange-600" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Đơn chờ duyệt</p>
            <p className="text-2xl font-bold text-gray-900">{pendingCount}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Quick Actions */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h2 className="font-semibold text-gray-900 mb-4">Thao tác nhanh</h2>
          <div className="space-y-2">
            <button
              onClick={() => setShowLeaveModal(true)}
              className="w-full flex items-center gap-3 p-3 bg-mint-50 hover:bg-mint-100 text-mint-700 rounded-lg transition-colors text-left"
            >
              <Plus size={18} />
              <span className="font-medium">Tạo đơn xin phép</span>
            </button>
            <Link
              to="/my/attendance"
              className="flex items-center gap-3 p-3 bg-green-50 hover:bg-green-100 text-green-700 rounded-lg transition-colors"
            >
              <Calendar size={18} />
              <span className="font-medium">Xem lịch chấm công</span>
            </Link>
            <Link
              to="/my/requests"
              className="flex items-center gap-3 p-3 bg-purple-50 hover:bg-purple-100 text-purple-700 rounded-lg transition-colors"
            >
              <FileText size={18} />
              <span className="font-medium">Xem đơn từ của tôi</span>
            </Link>
          </div>
        </div>

        {/* Recent Attendance */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h2 className="font-semibold text-gray-900 mb-4">Chấm công gần đây</h2>
          {attendanceLoading ? (
            <div className="flex justify-center py-4"><LoadingSpinner size="sm" /></div>
          ) : recentLogs.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-4">Không có dữ liệu</p>
          ) : (
            <div className="space-y-1">
              {recentLogs.map((log) => (
                <div
                  key={log.id}
                  className="flex items-center justify-between py-2.5 border-b border-gray-50 last:border-0"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-800 capitalize">
                      {format(new Date(log.date), 'EEE, dd/MM', { locale: vi })}
                    </p>
                    <p className="text-xs text-gray-500">
                      {log.check_in ? format(new Date(log.check_in), 'HH:mm') : '—'} →{' '}
                      {log.check_out ? format(new Date(log.check_out), 'HH:mm') : '—'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {log.work_hours != null && (
                      <span className="text-sm text-gray-500">{log.work_hours.toFixed(1)}h</span>
                    )}
                    <CheckCircle size={14} className="text-green-500" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Create Leave Modal */}
      <Modal
        isOpen={showLeaveModal}
        onClose={() => setShowLeaveModal(false)}
        title="Tạo đơn xin phép"
        size="md"
        footer={
          <>
            <button onClick={() => setShowLeaveModal(false)} className="btn-secondary">Hủy</button>
            <button
              onClick={handleCreateLeave}
              disabled={createLeaveMutation.isPending}
              className="btn-primary"
            >
              {createLeaveMutation.isPending ? <LoadingSpinner size="sm" /> : 'Gửi đơn'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Loại đơn</label>
            <select
              className="input-field"
              value={leaveForm.type}
              onChange={(e) => setLeaveForm({ ...leaveForm, type: e.target.value as typeof leaveForm.type })}
            >
              <option value="nghi_phep">Nghỉ phép</option>
              <option value="di_muon">Đi muộn</option>
              <option value="ve_som">Về sớm</option>
            </select>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Từ ngày giờ <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                className={`input-field ${leaveErrors.start_datetime ? 'border-red-400' : ''}`}
                value={leaveForm.start_datetime}
                onChange={(e) => setLeaveForm({ ...leaveForm, start_datetime: e.target.value })}
              />
              {leaveErrors.start_datetime && (
                <p className="text-red-500 text-xs mt-1">{leaveErrors.start_datetime}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Đến ngày giờ <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                className={`input-field ${leaveErrors.end_datetime ? 'border-red-400' : ''}`}
                value={leaveForm.end_datetime}
                onChange={(e) => setLeaveForm({ ...leaveForm, end_datetime: e.target.value })}
              />
              {leaveErrors.end_datetime && (
                <p className="text-red-500 text-xs mt-1">{leaveErrors.end_datetime}</p>
              )}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Lý do <span className="text-red-500">*</span>
            </label>
            <textarea
              className={`input-field resize-none h-24 ${leaveErrors.reason ? 'border-red-400' : ''}`}
              value={leaveForm.reason}
              onChange={(e) => setLeaveForm({ ...leaveForm, reason: e.target.value })}
              placeholder="Nhập lý do xin phép..."
            />
            {leaveErrors.reason && (
              <p className="text-red-500 text-xs mt-1">{leaveErrors.reason}</p>
            )}
          </div>
          {createLeaveMutation.isError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-red-700 text-sm">
                {createLeaveMutation.error?.message || 'Gửi đơn thất bại'}
              </p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}

export default MyDashboard
