import React, { useRef, useState, useCallback } from 'react'
import Webcam from 'react-webcam'
import { Camera, RefreshCw } from 'lucide-react'

interface WebcamCaptureProps {
  onCapture: (base64: string) => void
  // Gọi khi user bấm "Chụp lại" — parent có thể clear state ảnh đã chụp
  // nếu cần. Cần thiết cho luồng multi-pose: nếu không có hook này, parent
  // có thể vô tình lưu ảnh cũ vì nó vẫn còn trong state.
  onRetake?: () => void
}

const WebcamCapture: React.FC<WebcamCaptureProps> = ({ onCapture, onRetake }) => {
  const webcamRef = useRef<Webcam>(null)
  const [capturedImage, setCapturedImage] = useState<string | null>(null)
  const [cameraError, setCameraError] = useState(false)

  const handleCapture = useCallback(() => {
    const imageSrc = webcamRef.current?.getScreenshot()
    if (imageSrc) {
      setCapturedImage(imageSrc)
      // Bỏ phần prefix data URL để chỉ lấy chuỗi base64 thuần
      const base64 = imageSrc.split(',')[1]
      onCapture(base64)
    }
  }, [onCapture])

  const handleRetake = () => {
    setCapturedImage(null)
    onRetake?.()
  }

  const videoConstraints = {
    width: 480,
    height: 360,
    facingMode: 'user',
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative w-full max-w-sm rounded-xl overflow-hidden bg-gray-900 aspect-video">
        {!capturedImage ? (
          <>
            {!cameraError ? (
              <Webcam
                ref={webcamRef}
                audio={false}
                screenshotFormat="image/jpeg"
                videoConstraints={videoConstraints}
                onUserMediaError={() => setCameraError(true)}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-white gap-2 py-16">
                <Camera size={48} className="opacity-40" />
                <p className="text-sm opacity-60">Không thể truy cập camera</p>
                <p className="text-xs opacity-40">Kiểm tra quyền truy cập camera trong trình duyệt</p>
              </div>
            )}
            {/* Khung hướng dẫn vị trí khuôn mặt */}
            {!cameraError && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-40 h-48 border-2 border-mint-400 border-dashed rounded-full opacity-60" />
              </div>
            )}
          </>
        ) : (
          <img src={capturedImage} alt="Ảnh đã chụp" className="w-full h-full object-cover" />
        )}
      </div>

      <div className="flex gap-3">
        {!capturedImage ? (
          <button
            onClick={handleCapture}
            disabled={cameraError}
            className="flex items-center gap-2 bg-mint-600 hover:bg-mint-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2.5 rounded-lg font-medium transition-colors"
          >
            <Camera size={18} />
            Chụp ảnh
          </button>
        ) : (
          <button
            onClick={handleRetake}
            className="flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-6 py-2.5 rounded-lg font-medium transition-colors"
          >
            <RefreshCw size={18} />
            Chụp lại
          </button>
        )}
      </div>

    </div>
  )
}

export default WebcamCapture
