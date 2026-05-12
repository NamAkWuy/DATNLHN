import React from 'react'

type BadgeVariant =
  | 'active'
  | 'inactive'
  | 'cho_duyet'
  | 'da_duyet'
  | 'tu_choi'
  | 'da_huy'
  | 'face'
  | 'rfid'
  | 'manual'
  | 'nghi_phep'
  | 'di_muon'
  | 've_som'
  | 'present'
  | 'absent'
  | 'late'
  | 'leave'
  | 'disabled'
  | string

interface StatusBadgeProps {
  status: BadgeVariant
  label?: string
  size?: 'sm' | 'md'
}

const badgeConfig: Record<string, { bg: string; text: string; label: string }> = {
  active: { bg: 'bg-mint-100', text: 'text-mint-700', label: 'Đang hoạt động' },
  inactive: { bg: 'bg-gray-100', text: 'text-gray-600', label: 'Không hoạt động' },
  disabled: { bg: 'bg-rose-100', text: 'text-rose-700', label: 'Vô hiệu hóa' },
  cho_duyet: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Chờ duyệt' },
  da_duyet: { bg: 'bg-mint-100', text: 'text-mint-700', label: 'Đã duyệt' },
  tu_choi: { bg: 'bg-rose-100', text: 'text-rose-700', label: 'Từ chối' },
  da_huy: { bg: 'bg-gray-100', text: 'text-gray-600', label: 'Đã hủy' },
  face: { bg: 'bg-sky-100', text: 'text-sky-700', label: 'Nhận diện' },
  rfid: { bg: 'bg-mint-100', text: 'text-mint-700', label: 'RFID' },
  manual: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Thủ công' },
  nghi_phep: { bg: 'bg-sky-100', text: 'text-sky-700', label: 'Nghỉ phép' },
  di_muon: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Đi muộn' },
  ve_som: { bg: 'bg-orange-100', text: 'text-orange-700', label: 'Về sớm' },
  present: { bg: 'bg-mint-100', text: 'text-mint-700', label: 'Có mặt' },
  absent: { bg: 'bg-rose-100', text: 'text-rose-700', label: 'Vắng mặt' },
  late: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Đi muộn' },
  leave: { bg: 'bg-sky-100', text: 'text-sky-700', label: 'Nghỉ phép' },
}

const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, size = 'sm' }) => {
  const config = badgeConfig[status] || {
    bg: 'bg-gray-100',
    text: 'text-gray-600',
    label: status,
  }

  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${config.bg} ${config.text} ${sizeClass}`}
    >
      {label || config.label}
    </span>
  )
}

export default StatusBadge
