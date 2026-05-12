import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
import { Download, FileSpreadsheet, FileText } from 'lucide-react'
import { reportApi } from '../../services/api'
import type { AttendanceReport } from '../../types'
import PageTitle from '../../components/PageTitle'
import LoadingSpinner from '../../components/LoadingSpinner'

const Reports: React.FC = () => {
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())

  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ['summary'],
    queryFn: reportApi.getSummary,
  })

  const { data: reportData, isLoading: reportLoading } = useQuery({
    queryKey: ['attendance-report', month, year],
    queryFn: () => reportApi.getAttendanceReport(month, year),
  })

  const summary = summaryData?.data
  const reports: AttendanceReport[] = reportData?.data?.records || []

  const handleExportExcel = async () => {
    try {
      const blob = await reportApi.exportExcel(month, year)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `bao-cao-cham-cong-${month}-${year}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Xuất Excel thất bại')
    }
  }

  const handleExportPDF = async () => {
    try {
      const blob = await reportApi.exportPDF(month, year)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `bao-cao-cham-cong-${month}-${year}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Xuất PDF thất bại')
    }
  }

  const months = Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `Tháng ${i + 1}` }))
  const years = [now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1]

  // Dữ liệu cho biểu đồ, lấy từ danh sách báo cáo
  const chartData = reports.slice(0, 10).map((r) => ({
    name: r.full_name.split(' ').pop() || r.full_name,
    worked: r.total_days_worked,
    late: r.late_count,
    absent: r.absent_count,
  }))

  return (
    <div className="space-y-6">
      <PageTitle
        title="Báo cáo Chấm công"
        actions={
          <div className="flex gap-2">
            <button
              onClick={handleExportExcel}
              className="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <FileSpreadsheet size={16} />
              Excel
            </button>
            <button
              onClick={handleExportPDF}
              className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <FileText size={16} />
              PDF
            </button>
          </div>
        }
      />

      {/* Filter */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex gap-3 items-center flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Tháng:</label>
          <select
            value={month}
            onChange={(e) => setMonth(Number(e.target.value))}
            className="input-field w-auto"
          >
            {months.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Năm:</label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="input-field w-auto"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        <span className="text-sm text-gray-500">
          Báo cáo tháng {month}/{year}
        </span>
      </div>

      {/* Summary Cards */}
      {summaryLoading ? (
        <div className="flex justify-center py-8"><LoadingSpinner /></div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Tổng nhân viên', value: summary?.total_employees, color: 'bg-mint-50 text-mint-700' },
            { label: 'Có mặt hôm nay', value: summary?.present_today, color: 'bg-green-50 text-green-700' },
            { label: 'Đơn chờ duyệt', value: summary?.pending_requests, color: 'bg-yellow-50 text-yellow-700' },
            { label: 'Đi muộn tháng này', value: summary?.late_this_month, color: 'bg-orange-50 text-orange-700' },
          ].map((item) => (
            <div key={item.label} className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <p className="text-sm text-gray-500">{item.label}</p>
              <p className={`text-3xl font-bold mt-1 ${item.color.split(' ')[1]}`}>
                {item.value ?? '—'}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Chart */}
      {reports.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h2 className="text-base font-semibold text-gray-900 mb-4">
            Biểu đồ chấm công tháng {month}/{year}
          </h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} barSize={18}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend iconSize={12} wrapperStyle={{ fontSize: '12px' }} />
              <Bar dataKey="worked" name="Ngày làm" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="late" name="Đi muộn" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              <Bar dataKey="absent" name="Vắng" fill="#ef4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">
            Bảng chi tiết tháng {month}/{year}
          </h2>
          <button onClick={handleExportExcel} className="flex items-center gap-1.5 text-green-600 hover:bg-green-50 px-3 py-1.5 rounded-lg text-sm transition-colors">
            <Download size={14} />
            Tải xuống
          </button>
        </div>

        {reportLoading ? (
          <div className="flex justify-center py-16">
            <LoadingSpinner size="md" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead>
                <tr>
                  <th className="table-header">Mã NV</th>
                  <th className="table-header">Họ tên</th>
                  <th className="table-header">Phòng ban</th>
                  <th className="table-header text-center">Ngày công</th>
                  <th className="table-header text-center">Số giờ làm</th>
                  <th className="table-header text-center">Đi muộn</th>
                  <th className="table-header text-center">Về sớm</th>
                  <th className="table-header text-center">Nghỉ phép</th>
                  <th className="table-header text-center">Vắng mặt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {reports.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-12 text-center text-gray-400 text-sm">
                      Không có dữ liệu
                    </td>
                  </tr>
                ) : (
                  reports.map((r) => (
                    <tr key={r.employee_id} className="table-row">
                      <td className="table-cell font-mono text-xs text-gray-500">
                        {r.employee_code}
                      </td>
                      <td className="table-cell font-medium">{r.full_name}</td>
                      <td className="table-cell text-gray-500">{r.department}</td>
                      <td className="table-cell text-center">
                        <span className="font-semibold text-mint-600">{r.total_days_worked}</span>
                      </td>
                      <td className="table-cell text-center">
                        <span className="font-semibold text-blue-600">
                          {r.total_work_hours?.toLocaleString('vi-VN', { maximumFractionDigits: 2 }) ?? 0}h
                        </span>
                      </td>
                      <td className="table-cell text-center">
                        <span className={r.late_count > 0 ? 'text-yellow-600 font-medium' : 'text-gray-400'}>
                          {r.late_count}
                        </span>
                      </td>
                      <td className="table-cell text-center">
                        <span className={r.early_leave_count > 0 ? 'text-orange-600 font-medium' : 'text-gray-400'}>
                          {r.early_leave_count}
                        </span>
                      </td>
                      <td className="table-cell text-center">
                        <span className="text-gray-600">{r.leave_days}</span>
                      </td>
                      <td className="table-cell text-center">
                        <span className={r.absent_count > 0 ? 'text-red-600 font-medium' : 'text-gray-400'}>
                          {r.absent_count}
                        </span>
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

export default Reports
