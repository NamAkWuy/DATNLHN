import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { attendanceApi } from '../../services/api'
import type { AttendanceLog } from '../../types'
import PageTitle from '../../components/PageTitle'
import LoadingSpinner from '../../components/LoadingSpinner'
import { format, getDaysInMonth, getDay } from 'date-fns'
import { vi } from 'date-fns/locale'

const MyAttendance: React.FC = () => {
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())

  const { data, isLoading } = useQuery({
    queryKey: ['my-attendance', month, year],
    queryFn: () => attendanceApi.getMyAttendance({ month, year }),
  })

  const logs: AttendanceLog[] = data?.data || []

  const logsByDate: Record<string, AttendanceLog> = {}
  logs.forEach((l) => {
    logsByDate[l.date] = l
  })

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(year - 1) }
    else setMonth(month - 1)
  }

  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(year + 1) }
    else setMonth(month + 1)
  }

  const getDayStatus = (dateStr: string): { label: string; color: string; bg: string } => {
    const date = new Date(dateStr)
    const dayOfWeek = getDay(date) // 0=Sun, 6=Sat
    if (dayOfWeek === 0 || dayOfWeek === 6) {
      return { label: 'Cuối tuần', color: 'text-gray-400', bg: 'bg-gray-50' }
    }
    const log = logsByDate[dateStr]
    if (!log) {
      if (new Date(dateStr) > now) return { label: '—', color: 'text-gray-300', bg: '' }
      return { label: 'Vắng mặt', color: 'text-red-600', bg: 'bg-red-50' }
    }
    if (log.check_in) {
      const h = new Date(log.check_in).getHours()
      const m = new Date(log.check_in).getMinutes()
      if (h > 8 || (h === 8 && m > 5)) {
        return { label: 'Đi muộn', color: 'text-yellow-600', bg: 'bg-yellow-50' }
      }
      return { label: 'Có mặt', color: 'text-green-600', bg: 'bg-green-50' }
    }
    return { label: 'Vắng mặt', color: 'text-red-600', bg: 'bg-red-50' }
  }

  // Tạo danh sách các ngày trong tháng đang xem
  const daysInMonth = getDaysInMonth(new Date(year, month - 1))
  const daysArray = Array.from({ length: daysInMonth }, (_, i) => {
    const d = i + 1
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    return { day: d, dateStr }
  })

  // Thống kê tổng hợp
  const presentCount = logs.filter((l) => l.check_in).length
  const lateCount = logs.filter((l) => {
    if (!l.check_in) return false
    const h = new Date(l.check_in).getHours()
    const m2 = new Date(l.check_in).getMinutes()
    return h > 8 || (h === 8 && m2 > 5)
  }).length
  const totalHours = logs.reduce((sum, l) => sum + (l.work_hours || 0), 0)

  return (
    <div>
      <PageTitle title="Chấm công của tôi" />

      {/* Month Navigation */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 mb-4">
        <div className="flex items-center justify-between">
          <button onClick={prevMonth} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
            <ChevronLeft size={20} />
          </button>
          <div className="text-center">
            <p className="text-lg font-bold text-gray-900">
              Tháng {month}, {year}
            </p>
            <p className="text-sm text-gray-500">
              {presentCount} ngày công · {lateCount} đi muộn · {totalHours.toFixed(1)}h tổng
            </p>
          </div>
          <button onClick={nextMonth} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
            <ChevronRight size={20} />
          </button>
        </div>
      </div>

      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-green-50 border border-green-100 rounded-xl p-3 text-center">
          <p className="text-2xl font-bold text-green-700">{presentCount}</p>
          <p className="text-xs text-green-600 mt-0.5">Ngày có mặt</p>
        </div>
        <div className="bg-yellow-50 border border-yellow-100 rounded-xl p-3 text-center">
          <p className="text-2xl font-bold text-yellow-700">{lateCount}</p>
          <p className="text-xs text-yellow-600 mt-0.5">Đi muộn</p>
        </div>
        <div className="bg-mint-50 border border-mint-100 rounded-xl p-3 text-center">
          <p className="text-2xl font-bold text-mint-700">{totalHours.toFixed(1)}h</p>
          <p className="text-xs text-mint-600 mt-0.5">Tổng giờ làm</p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <LoadingSpinner size="md" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead>
                <tr>
                  <th className="table-header">Ngày</th>
                  <th className="table-header">Thứ</th>
                  <th className="table-header">Giờ vào</th>
                  <th className="table-header">Giờ ra</th>
                  <th className="table-header">Số giờ</th>
                  <th className="table-header">Trạng thái</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {daysArray.map(({ day, dateStr }) => {
                  const log = logsByDate[dateStr]
                  const dayOfWeek = getDay(new Date(dateStr))
                  const isWeekend = dayOfWeek === 0 || dayOfWeek === 6
                  const status = getDayStatus(dateStr)
                  const isFuture = new Date(dateStr) > now

                  return (
                    <tr key={dateStr} className={`${isWeekend ? 'bg-gray-50' : 'hover:bg-gray-50'} border-b border-gray-100`}>
                      <td className="table-cell font-medium">
                        {String(day).padStart(2, '0')}/{String(month).padStart(2, '0')}
                      </td>
                      <td className="table-cell text-gray-500 capitalize">
                        {format(new Date(dateStr), 'EEE', { locale: vi })}
                      </td>
                      <td className="table-cell">
                        {log?.check_in
                          ? format(new Date(log.check_in), 'HH:mm')
                          : '—'}
                      </td>
                      <td className="table-cell">
                        {log?.check_out
                          ? format(new Date(log.check_out), 'HH:mm')
                          : '—'}
                      </td>
                      <td className="table-cell">
                        {log?.work_hours != null ? `${log.work_hours.toFixed(1)}h` : '—'}
                      </td>
                      <td className="table-cell">
                        {!isFuture ? (
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${status.bg} ${status.color}`}>
                            {status.label}
                          </span>
                        ) : (
                          <span className="text-gray-300 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default MyAttendance
