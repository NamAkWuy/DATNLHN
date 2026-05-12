import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import {
  Users,
  UserCheck,
  UserX,
  FileText,
  Clock,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { reportApi, leaveApi, attendanceApi } from '../../services/api'
import { format } from 'date-fns'
import StatusBadge from '../../components/StatusBadge'
import LoadingSpinner from '../../components/LoadingSpinner'
import type { LeaveRequest } from '../../types'

const StatCard: React.FC<{
  title: string
  value: number | string
  icon: React.ReactNode
  color: string
  bgColor: string
}> = ({ title, value, icon, color, bgColor }) => (
  <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex items-center gap-4">
    <div className={`w-12 h-12 ${bgColor} rounded-xl flex items-center justify-center flex-shrink-0`}>
      <div className={color}>{icon}</div>
    </div>
    <div>
      <p className="text-sm text-gray-500 font-medium">{title}</p>
      <p className="text-2xl font-bold text-gray-900 mt-0.5">{value}</p>
    </div>
  </div>
)

const Dashboard: React.FC = () => {
  const queryClient = useQueryClient()

  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ['summary'],
    queryFn: reportApi.getSummary,
  })

  const { data: chartData, isLoading: chartLoading } = useQuery({
    queryKey: ['chart-weekly'],
    queryFn: reportApi.getChartData,
  })

  const { data: recentAttendance, isLoading: attendanceLoading } = useQuery({
    queryKey: ['attendance-recent'],
    queryFn: () => attendanceApi.getLogs({ page: 1, page_size: 10 }),
  })

  const { data: pendingLeave, isLoading: leaveLoading } = useQuery({
    queryKey: ['leave-pending'],
    queryFn: () => leaveApi.getAll({ status: 'cho_duyet', page: 1, page_size: 10 }),
  })

  const approveMutation = useMutation({
    mutationFn: leaveApi.approve,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leave-pending'] })
      queryClient.invalidateQueries({ queryKey: ['summary'] })
      queryClient.invalidateQueries({ queryKey: ['chart-weekly'] })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      leaveApi.reject(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leave-pending'] })
      queryClient.invalidateQueries({ queryKey: ['summary'] })
      queryClient.invalidateQueries({ queryKey: ['chart-weekly'] })
    },
  })

  const summary = summaryData?.data
  const chartPoints = chartData?.data ?? []
  const attendanceLogs = recentAttendance?.data?.items || []
  const pendingRequests = pendingLeave?.data?.items || []

  const stats = [
    {
      title: 'Tổng nhân viên',
      value: summary?.total_employees ?? '—',
      icon: <Users size={22} />,
      color: 'text-mint-600',
      bgColor: 'bg-mint-50',
    },
    {
      title: 'Có mặt hôm nay',
      value: summary?.present_today ?? '—',
      icon: <UserCheck size={22} />,
      color: 'text-green-600',
      bgColor: 'bg-green-50',
    },
    {
      title: 'Vắng mặt',
      value: summary?.absent_today ?? '—',
      icon: <UserX size={22} />,
      color: 'text-red-600',
      bgColor: 'bg-red-50',
    },
    {
      title: 'Đơn chờ duyệt',
      value: summary?.pending_requests ?? '—',
      icon: <FileText size={22} />,
      color: 'text-yellow-600',
      bgColor: 'bg-yellow-50',
    },
    {
      title: 'Đi muộn tháng này',
      value: summary?.late_this_month ?? '—',
      icon: <Clock size={22} />,
      color: 'text-orange-600',
      bgColor: 'bg-orange-50',
    },
  ]

  const typeLabel: Record<string, string> = {
    nghi_phep: 'Nghỉ phép',
    di_muon: 'Đi muộn',
    ve_som: 'Về sớm',
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Tổng quan</h1>
        <p className="text-sm text-gray-500 mt-1">
          {format(new Date(), 'EEEE, dd/MM/yyyy')} · Hệ thống Chấm công & Quản lý Nhân sự
        </p>
      </div>

      {/* Stats */}
      {summaryLoading ? (
        <div className="flex justify-center py-8">
          <LoadingSpinner size="md" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
          {stats.map((stat) => (
            <StatCard key={stat.title} {...stat} />
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Chart */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h2 className="text-base font-semibold text-gray-900 mb-4">
            Điểm danh 7 ngày gần nhất
          </h2>
          {chartLoading ? (
            <div className="flex justify-center items-center" style={{ height: 240 }}>
              <LoadingSpinner size="sm" />
            </div>
          ) : chartPoints.length === 0 ? (
            <div className="flex justify-center items-center text-gray-400 text-sm" style={{ height: 240 }}>
              Chưa có dữ liệu chấm công
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartPoints} barSize={20}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip />
                <Legend iconSize={12} wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="present" name="Có mặt" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="absent" name="Vắng mặt" fill="#f87171" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Pending Requests */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h2 className="text-base font-semibold text-gray-900 mb-4">
            Đơn chờ duyệt
          </h2>
          {leaveLoading ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner size="sm" />
            </div>
          ) : pendingRequests.length === 0 ? (
            <div className="text-center py-8 text-gray-400 text-sm">
              Không có đơn chờ duyệt
            </div>
          ) : (
            <div className="space-y-3 max-h-64 overflow-y-auto">
              {pendingRequests.map((req: LeaveRequest) => (
                <div
                  key={req.id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                >
                  <div className="min-w-0 mr-3">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {req.employee?.full_name || `NV#${req.employee_id}`}
                    </p>
                    <p className="text-xs text-gray-500">
                      {typeLabel[req.type] || req.type} ·{' '}
                      {format(new Date(req.start_datetime), 'dd/MM HH:mm')}
                    </p>
                    <p className="text-xs text-gray-400 truncate">{req.reason}</p>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <button
                      onClick={() => approveMutation.mutate(req.id)}
                      disabled={approveMutation.isPending}
                      className="p-1.5 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                      title="Duyệt"
                    >
                      <CheckCircle size={18} />
                    </button>
                    <button
                      onClick={() => rejectMutation.mutate({ id: req.id, reason: 'Không được chấp thuận' })}
                      disabled={rejectMutation.isPending}
                      className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="Từ chối"
                    >
                      <XCircle size={18} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent Attendance */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">Điểm danh gần đây</h2>
        </div>
        {attendanceLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner size="sm" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="bg-gray-50">
                  <th className="table-header">Nhân viên</th>
                  <th className="table-header">Ngày</th>
                  <th className="table-header">Giờ vào</th>
                  <th className="table-header">Giờ ra</th>
                  <th className="table-header">Phương thức</th>
                  <th className="table-header">Số giờ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {attendanceLogs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-gray-400 text-sm">
                      Không có dữ liệu
                    </td>
                  </tr>
                ) : (
                  attendanceLogs.map((log) => (
                    <tr key={log.id} className="table-row">
                      <td className="table-cell font-medium">{log.employee?.full_name || `NV#${log.employee_id}`}</td>
                      <td className="table-cell">{format(new Date(log.date), 'dd/MM/yyyy')}</td>
                      <td className="table-cell">
                        {log.check_in ? format(new Date(log.check_in), 'HH:mm') : '—'}
                      </td>
                      <td className="table-cell">
                        {log.check_out ? format(new Date(log.check_out), 'HH:mm') : '—'}
                      </td>
                      <td className="table-cell">
                        <StatusBadge status={log.method} />
                      </td>
                      <td className="table-cell">
                        {log.work_hours ? `${log.work_hours.toFixed(1)}h` : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default Dashboard
