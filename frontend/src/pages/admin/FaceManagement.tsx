import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Scan, Trash2, CheckCircle, XCircle, Search, ArrowLeft, Glasses } from 'lucide-react'
import { employeeApi, faceApi } from '../../services/api'
import type { Employee } from '../../types'
import PageTitle from '../../components/PageTitle'
import Modal from '../../components/Modal'
import LoadingSpinner from '../../components/LoadingSpinner'
import WebcamCapture from '../../components/WebcamCapture'

// Kịch bản multi-pose enrollment: 5 pose bao quát cả trạng thái có/không kính.
// Pose đầu là TEMPLATE CHÍNH (primary, không bị xóa khi gallery đầy), các pose
// sau là template phụ trong gallery (gallery 8 slot trên backend, dành 3 slot
// cuối cho adaptive learning tự bổ sung khi chấm công thành công).
//
// Vì sao bao gồm cả "có kính": ArcFace nhạy cảm với gọng kính + phản chiếu
// tròng kính. Nếu chỉ enroll một trạng thái, người đeo kính không nhất quán
// (lúc đeo lúc không) sẽ bị reject nửa số lần chấm công.
const POSE_PROMPTS = [
  { main: 'Nhìn THẲNG vào camera', sub: 'Bỏ kính (nếu đang đeo)', primary: true },
  { main: 'Quay nhẹ sang TRÁI ~15°', sub: 'Bỏ kính', primary: false },
  { main: 'Quay nhẹ sang PHẢI ~15°', sub: 'Bỏ kính', primary: false },
  { main: 'Nhìn THẲNG vào camera', sub: 'ĐEO kính (nếu có)', primary: false, withGlasses: true },
  { main: 'Quay nhẹ một bên', sub: 'ĐEO kính (nếu có)', primary: false, withGlasses: true },
]
const TOTAL_POSES = POSE_PROMPTS.length

// Footer của modal đăng ký — tách riêng để giữ render chính của Modal gọn.
// 4 trạng thái: success / đang chụp pose / review trước submit / đang submit.
function renderRegisterFooter(args: {
  registerSuccess: boolean
  poseIdx: number
  totalPoses: number
  currentBase64: string | null
  isPending: boolean
  onClose: () => void
  onConfirmPose: () => void
  onGoBack: () => void
  onSubmit: () => void
}) {
  const {
    registerSuccess, poseIdx, totalPoses, currentBase64, isPending,
    onClose, onConfirmPose, onGoBack, onSubmit,
  } = args

  if (registerSuccess) {
    return (
      <button onClick={onClose} className="btn-primary">Đóng</button>
    )
  }

  // Đã chụp đủ → màn review + submit
  if (poseIdx >= totalPoses) {
    return (
      <>
        <button
          onClick={onGoBack}
          disabled={isPending}
          className="btn-secondary flex items-center gap-1.5"
        >
          <ArrowLeft size={14} /> Quay lại pose cuối
        </button>
        <button
          onClick={onSubmit}
          disabled={isPending}
          className="btn-primary flex items-center gap-2"
        >
          {isPending ? (
            <><LoadingSpinner size="sm" /> Đang xử lý...</>
          ) : (
            <><Scan size={16} /> Đăng ký khuôn mặt</>
          )}
        </button>
      </>
    )
  }

  // Đang chụp pose
  const isLastPose = poseIdx === totalPoses - 1
  return (
    <>
      <button onClick={onClose} className="btn-secondary">Hủy</button>
      {poseIdx > 0 && (
        <button
          onClick={onGoBack}
          className="btn-secondary flex items-center gap-1.5"
        >
          <ArrowLeft size={14} /> Pose trước
        </button>
      )}
      <button
        onClick={onConfirmPose}
        disabled={!currentBase64}
        className="btn-primary"
      >
        {isLastPose ? 'Lưu & xem lại →' : 'Lưu pose này, tiếp →'}
      </button>
    </>
  )
}

const FaceManagement: React.FC = () => {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [registerTarget, setRegisterTarget] = useState<Employee | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Employee | null>(null)
  const [registerSuccess, setRegisterSuccess] = useState(false)

  // ─── State multi-pose ─────────────────────────────────────────────────────
  // poseIdx = pose hiện tại đang chụp (0..TOTAL_POSES). Khi = TOTAL_POSES,
  // user đã hoàn tất hết → hiện màn xác nhận trước khi gửi backend.
  // capturedPoses = các base64 đã CHỐT (sau khi user nhấn "Lưu pose này").
  // currentBase64 = base64 vừa chụp pose hiện tại, đang chờ chốt — null nếu
  // user đã chụp lại / chưa chụp.
  const [poseIdx, setPoseIdx] = useState(0)
  const [capturedPoses, setCapturedPoses] = useState<string[]>([])
  const [currentBase64, setCurrentBase64] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['employees-face', search],
    queryFn: () =>
      employeeApi.getAll({ search: search || undefined, page: 1, page_size: 100 }),
  })

  const registerMutation = useMutation({
    mutationFn: ({
      employee_id,
      image_base64,
      extra_images,
    }: {
      employee_id: number
      image_base64: string
      extra_images?: string[]
    }) => faceApi.register(employee_id, image_base64, extra_images),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employees-face'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      setRegisterSuccess(true)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: faceApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employees-face'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      setDeleteTarget(null)
    },
  })

  const employees: Employee[] = data?.data?.items || []

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
  }

  const resetEnrollState = () => {
    setPoseIdx(0)
    setCapturedPoses([])
    setCurrentBase64(null)
    setRegisterSuccess(false)
  }

  const openRegister = (emp: Employee) => {
    setRegisterTarget(emp)
    resetEnrollState()
  }

  const closeRegister = () => {
    setRegisterTarget(null)
    resetEnrollState()
    registerMutation.reset()
  }

  // Chốt pose hiện tại → lưu vào mảng, tiến tới pose tiếp theo.
  const confirmCurrentPose = () => {
    if (!currentBase64) return
    setCapturedPoses((prev) => [...prev, currentBase64])
    setCurrentBase64(null)
    setPoseIdx((idx) => idx + 1)
  }

  // Cho phép user quay lại chụp lại pose trước đó (vd: pose 3 chụp xong mới
  // nhận ra pose 2 bị mờ). Pop pose cuối khỏi mảng, lùi index.
  const goBackOnePose = () => {
    if (poseIdx === 0) return
    setCapturedPoses((prev) => prev.slice(0, -1))
    setCurrentBase64(null)
    setPoseIdx((idx) => idx - 1)
  }

  const handleSubmitAll = () => {
    if (!registerTarget || capturedPoses.length === 0) return
    const [primary, ...extras] = capturedPoses
    registerMutation.mutate({
      employee_id: registerTarget.id,
      image_base64: primary,
      extra_images: extras.length > 0 ? extras : undefined,
    })
  }

  const registeredCount = employees.filter((e) => e.has_face).length

  return (
    <div>
      <PageTitle
        title="Quản lý Khuôn mặt"
        subtitle={`${registeredCount}/${employees.length} nhân viên đã đăng ký`}
      />

      {/* Search */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 mb-4">
        <form onSubmit={handleSearch} className="flex gap-2 max-w-md">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Tìm kiếm nhân viên..."
              className="input-field pl-9"
            />
          </div>
          <button type="submit" className="btn-primary px-4">Tìm</button>
        </form>
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
                  <th className="table-header">Mã NV</th>
                  <th className="table-header">Họ tên</th>
                  <th className="table-header">Phòng ban</th>
                  <th className="table-header">Trạng thái khuôn mặt</th>
                  <th className="table-header text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {employees.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-gray-400 text-sm">
                      Không tìm thấy nhân viên
                    </td>
                  </tr>
                ) : (
                  employees.map((emp) => (
                    <tr key={emp.id} className="table-row">
                      <td className="table-cell font-mono text-xs text-gray-500">
                        {emp.employee_code}
                      </td>
                      <td className="table-cell font-medium">{emp.full_name}</td>
                      <td className="table-cell text-gray-500">
                        {emp.department?.name || '—'}
                      </td>
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          {emp.has_face ? (
                            <>
                              <CheckCircle size={16} className="text-green-500" />
                              <span className="text-green-700 text-sm font-medium">
                                Đã đăng ký
                              </span>
                              {/* Hiển thị số template — quan trọng để admin biết
                                  enrollment có thực sự đa pose hay chỉ 1 ảnh.
                                  Gallery 1/8 = chỉ ảnh chính → dễ false-reject;
                                  Gallery 5/8 = đã có đủ pose có/không kính. */}
                              {emp.face_template_count != null && (
                                <span
                                  className={`text-xs px-2 py-0.5 rounded-full font-mono ${
                                    emp.face_template_count >= 5
                                      ? 'bg-green-100 text-green-700'
                                      : emp.face_template_count >= 3
                                        ? 'bg-amber-100 text-amber-700'
                                        : 'bg-red-100 text-red-700'
                                  }`}
                                  title="Số template trong gallery / tối đa"
                                >
                                  {emp.face_template_count}/8
                                </span>
                              )}
                            </>
                          ) : (
                            <>
                              <XCircle size={16} className="text-gray-400" />
                              <span className="text-gray-400 text-sm">Chưa đăng ký</span>
                            </>
                          )}
                        </div>
                      </td>
                      <td className="table-cell text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openRegister(emp)}
                            className="flex items-center gap-1.5 text-xs bg-mint-50 hover:bg-mint-100 text-mint-700 px-3 py-1.5 rounded-lg transition-colors font-medium"
                          >
                            <Scan size={14} />
                            {emp.has_face ? 'Cập nhật' : 'Đăng ký'}
                          </button>
                          {emp.has_face && (
                            <button
                              onClick={() => setDeleteTarget(emp)}
                              className="flex items-center gap-1.5 text-xs bg-red-50 hover:bg-red-100 text-red-700 px-3 py-1.5 rounded-lg transition-colors font-medium"
                            >
                              <Trash2 size={14} />
                              Xóa
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Register Modal — multi-pose flow */}
      <Modal
        isOpen={!!registerTarget}
        onClose={closeRegister}
        title={`Đăng ký khuôn mặt - ${registerTarget?.full_name}`}
        size="md"
        footer={renderRegisterFooter({
          registerSuccess,
          poseIdx,
          totalPoses: TOTAL_POSES,
          currentBase64,
          isPending: registerMutation.isPending,
          onClose: closeRegister,
          onConfirmPose: confirmCurrentPose,
          onGoBack: goBackOnePose,
          onSubmit: handleSubmitAll,
        })}
      >
        {registerSuccess ? (
          <div className="text-center py-6">
            <CheckCircle size={56} className="text-green-500 mx-auto mb-3" />
            <p className="text-lg font-semibold text-gray-800">Đăng ký thành công!</p>
            <p className="text-gray-500 text-sm mt-1">
              Khuôn mặt của <strong>{registerTarget?.full_name}</strong> đã được lưu vào hệ thống.
            </p>
            {/* Báo cáo từ server: số template thực sự được lưu (= 1 primary +
                extras_added). Quan trọng cho debug: nếu extras_failed > 0 thì
                một số ảnh bị reject vì chất lượng kém, gallery sẽ ít hơn 5. */}
            {(() => {
              const extrasAdded = registerMutation.data?.data?.extras_added ?? 0
              const extrasFailed = registerMutation.data?.data?.extras_failed ?? 0
              const total = 1 + extrasAdded
              return (
                <div className="mt-4 inline-block text-left bg-mint-50 border border-mint-200 rounded-lg px-4 py-3 text-sm">
                  <p className="text-mint-800 font-semibold">
                    Đã lưu <span className="font-bold">{total}</span> template
                    {' '}({extrasAdded > 0 ? `1 ảnh chính + ${extrasAdded} ảnh phụ` : 'chỉ ảnh chính'})
                  </p>
                  {extrasFailed > 0 && (
                    <p className="text-amber-700 text-xs mt-1">
                      ⚠ {extrasFailed} ảnh bị bỏ vì không phát hiện được khuôn mặt /
                      ảnh quá mờ. Thử đăng ký lại nếu muốn đủ {TOTAL_POSES} pose.
                    </p>
                  )}
                </div>
              )
            })()}
          </div>
        ) : poseIdx < TOTAL_POSES ? (
          // ─── Đang chụp pose ──────────────────────────────────────────────
          <div className="space-y-4">
            {/* Stepper hiển thị 5 chấm đại diện 5 pose */}
            <div className="flex items-center justify-center gap-1.5">
              {POSE_PROMPTS.map((_, i) => (
                <div
                  key={i}
                  className={`h-1.5 rounded-full transition-all ${
                    i < poseIdx
                      ? 'w-8 bg-mint-500'
                      : i === poseIdx
                        ? 'w-12 bg-mint-600'
                        : 'w-8 bg-gray-200'
                  }`}
                />
              ))}
            </div>

            {/* Prompt cho pose hiện tại */}
            <div className="bg-mint-50 border border-mint-200 rounded-lg p-4 text-center">
              <p className="text-xs uppercase tracking-wider text-mint-600 font-semibold mb-1">
                Bước {poseIdx + 1}/{TOTAL_POSES}
                {POSE_PROMPTS[poseIdx].primary && ' • Ảnh chính'}
              </p>
              <p className="text-lg font-bold text-mint-800">
                {POSE_PROMPTS[poseIdx].main}
              </p>
              <p className="text-sm text-mint-700 mt-0.5 flex items-center justify-center gap-1.5">
                {POSE_PROMPTS[poseIdx].withGlasses && <Glasses size={14} />}
                {POSE_PROMPTS[poseIdx].sub}
              </p>
            </div>

            {/* WebcamCapture được remount mỗi lần đổi pose qua key={poseIdx}
                để clear trạng thái preview nội bộ. */}
            <WebcamCapture
              key={poseIdx}
              onCapture={(b64) => setCurrentBase64(b64)}
              onRetake={() => setCurrentBase64(null)}
            />

            {currentBase64 && (
              <p className="text-green-600 text-sm text-center font-medium">
                ✓ Đã chụp — nhấn "Lưu &amp; tiếp" hoặc "Chụp lại" trên webcam
              </p>
            )}
          </div>
        ) : (
          // ─── Review trước khi submit ─────────────────────────────────────
          <div className="space-y-4">
            <div className="bg-mint-50 border border-mint-200 rounded-lg p-4 text-sm text-mint-800">
              <p className="font-semibold mb-1">
                Đã chụp đủ {capturedPoses.length}/{TOTAL_POSES} pose
              </p>
              <p className="text-mint-700">
                Kiểm tra lại các ảnh. Nhấn <strong>Đăng ký khuôn mặt</strong> để gửi
                lên hệ thống, hoặc <strong>Quay lại pose cuối</strong> nếu muốn chụp lại.
              </p>
            </div>

            <div className="grid grid-cols-5 gap-2">
              {capturedPoses.map((b64, i) => (
                <div key={i} className="relative">
                  <img
                    src={`data:image/jpeg;base64,${b64}`}
                    alt={`Pose ${i + 1}`}
                    className="w-full aspect-square object-cover rounded-lg border-2 border-mint-300"
                  />
                  <span className="absolute top-1 left-1 bg-mint-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded">
                    {i + 1}
                  </span>
                  {POSE_PROMPTS[i].withGlasses && (
                    <span className="absolute bottom-1 right-1 bg-white/90 rounded p-0.5">
                      <Glasses size={10} className="text-mint-700" />
                    </span>
                  )}
                </div>
              ))}
            </div>

            {registerMutation.isError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-red-700 text-sm font-medium">Đăng ký thất bại</p>
                <p className="text-red-600 text-sm mt-1">
                  {(registerMutation.error as Error)?.message
                    || 'Có ảnh không phát hiện được khuôn mặt. Hãy quay lại chụp ảnh rõ hơn.'}
                </p>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Delete Confirm */}
      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Xác nhận xóa khuôn mặt"
        size="sm"
        footer={
          <>
            <button onClick={() => setDeleteTarget(null)} className="btn-secondary">Hủy</button>
            <button
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
              className="btn-danger"
            >
              {deleteMutation.isPending ? <LoadingSpinner size="sm" /> : 'Xóa'}
            </button>
          </>
        }
      >
        <p className="text-gray-600">
          Bạn có chắc chắn muốn xóa dữ liệu khuôn mặt của{' '}
          <span className="font-semibold">{deleteTarget?.full_name}</span>?
        </p>
        <p className="text-gray-400 text-sm mt-2">
          Nhân viên này sẽ không thể điểm danh bằng nhận diện khuôn mặt cho đến khi đăng ký lại.
        </p>
      </Modal>
    </div>
  )
}

export default FaceManagement
