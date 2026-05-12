import React, { useEffect, useRef, useState } from 'react'
import { Bell, Check, CheckCheck, Trash2, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notificationApi } from '../services/api'
import type { Notification } from '../types'

const POLL_INTERVAL_MS = 30_000

function formatRelative(iso: string): string {
  const now = new Date()
  const then = new Date(iso)
  const diffSec = Math.floor((now.getTime() - then.getTime()) / 1000)
  if (diffSec < 60) return 'Vừa xong'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} phút trước`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} giờ trước`
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)} ngày trước`
  return then.toLocaleDateString('vi-VN')
}

const NotificationDropdown: React.FC = () => {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: countData } = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => notificationApi.getUnreadCount(),
    refetchInterval: POLL_INTERVAL_MS,
    refetchOnWindowFocus: true,
  })

  const { data: listData, isLoading } = useQuery({
    queryKey: ['notifications', 'list'],
    queryFn: () => notificationApi.getAll({ page: 1, page_size: 20 }),
    enabled: open,
  })

  const markReadMutation = useMutation({
    mutationFn: (id: number) => notificationApi.markRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const markAllMutation = useMutation({
    mutationFn: () => notificationApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => notificationApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const clearAllMutation = useMutation({
    mutationFn: () => notificationApi.clearAll(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const unread = countData?.data?.unread ?? 0
  const items: Notification[] = listData?.data?.items ?? []

  const handleClick = (n: Notification) => {
    if (!n.is_read) markReadMutation.mutate(n.id)
    if (n.link) {
      setOpen(false)
      navigate(n.link)
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
        aria-label="Thông báo"
      >
        <Bell size={20} />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-red-500 text-white text-[10px] font-semibold rounded-full flex items-center justify-center">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-96 max-w-[calc(100vw-2rem)] bg-white border border-gray-200 rounded-xl shadow-lg z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">Thông báo</h3>
              {unread > 0 && (
                <p className="text-xs text-gray-500">{unread} thông báo chưa đọc</p>
              )}
            </div>
            <div className="flex items-center gap-1">
              {unread > 0 && (
                <button
                  onClick={() => markAllMutation.mutate()}
                  className="flex items-center gap-1 text-xs text-mint-600 hover:bg-mint-50 px-2 py-1 rounded transition-colors"
                  title="Đánh dấu tất cả đã đọc"
                >
                  <CheckCheck size={14} />
                  <span>Đã đọc tất cả</span>
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-600 rounded"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {isLoading && (
              <div className="px-4 py-8 text-center text-sm text-gray-400">Đang tải...</div>
            )}
            {!isLoading && items.length === 0 && (
              <div className="px-4 py-10 text-center">
                <Bell size={32} className="mx-auto text-gray-300 mb-2" />
                <p className="text-sm text-gray-500">Bạn chưa có thông báo nào.</p>
              </div>
            )}
            {!isLoading &&
              items.map((n) => (
                <div
                  key={n.id}
                  className={`group flex gap-3 px-4 py-3 border-b border-gray-100 last:border-b-0 cursor-pointer transition-colors ${
                    n.is_read ? 'hover:bg-gray-50' : 'bg-mint-50/40 hover:bg-mint-50'
                  }`}
                  onClick={() => handleClick(n)}
                >
                  <div className="flex-shrink-0 mt-1">
                    <span
                      className={`block w-2 h-2 rounded-full ${
                        n.is_read ? 'bg-gray-300' : 'bg-mint-500'
                      }`}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p
                      className={`text-sm leading-snug ${
                        n.is_read ? 'text-gray-700' : 'font-semibold text-gray-900'
                      }`}
                    >
                      {n.title}
                    </p>
                    <p className="text-xs text-gray-600 mt-0.5 line-clamp-2">{n.message}</p>
                    <p className="text-[11px] text-gray-400 mt-1">{formatRelative(n.created_at)}</p>
                  </div>
                  <div className="flex-shrink-0 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {!n.is_read && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          markReadMutation.mutate(n.id)
                        }}
                        className="p-1 text-gray-400 hover:text-mint-600 rounded"
                        title="Đánh dấu đã đọc"
                      >
                        <Check size={14} />
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteMutation.mutate(n.id)
                      }}
                      className="p-1 text-gray-400 hover:text-red-600 rounded"
                      title="Xóa"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
          </div>

          {items.length > 0 && (
            <div className="px-4 py-2 border-t border-gray-100 bg-gray-50">
              <button
                onClick={() => clearAllMutation.mutate()}
                className="w-full text-xs text-gray-500 hover:text-red-600 py-1 transition-colors"
              >
                Xóa tất cả thông báo
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default NotificationDropdown
