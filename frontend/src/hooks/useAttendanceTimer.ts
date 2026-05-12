import { useState, useEffect } from 'react'
import { format } from 'date-fns'
import { vi } from 'date-fns/locale'

export const useAttendanceTimer = () => {
  const [currentTime, setCurrentTime] = useState(new Date())

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date())
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  const formattedTime = format(currentTime, 'HH:mm:ss')
  const formattedDate = format(currentTime, 'EEEE, dd/MM/yyyy', { locale: vi })
  const formattedDateShort = format(currentTime, 'dd/MM/yyyy')

  return {
    currentTime,
    formattedTime,
    formattedDate,
    formattedDateShort,
  }
}
