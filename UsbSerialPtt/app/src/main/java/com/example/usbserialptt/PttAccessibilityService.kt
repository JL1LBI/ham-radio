package com.example.usbserialptt // ← ご自身のパッケージ名に合わせてください

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.graphics.Path
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import androidx.core.content.ContextCompat
import com.hoho.android.usbserial.driver.UsbSerialPort
import com.hoho.android.usbserial.driver.UsbSerialProber
import java.io.IOException

class PttAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "UsbSerialPtt"
        const val PREFS_NAME = "ptt_prefs"
        const val KEY_PTT_X = "ptt_x"
        const val KEY_PTT_Y = "ptt_y"
        const val KEY_TARGET_PIN = "target_pin"
        const val KEY_INVERT_LOGIC = "invert_logic"

        @Volatile var isServiceRunning = false
        @Volatile var statusText = "サービス未起動"
        @Volatile var lastPinRawState: Boolean? = null
        @Volatile var instance: PttAccessibilityService? = null
    }

    private lateinit var prefs: SharedPreferences
    private lateinit var usbManager: UsbManager
    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile private var pollingActive = false
    private var pollingThread: Thread? = null
    private var serialPort: UsbSerialPort? = null

    // PTT制御用（すべてmainHandler上で扱う）
    private var isPttDesired = false
    private var isHolding = false
    private val holdMaxDurationMs = 55_000L // 単一ジェスチャー上限(60秒)未満
    private val totTimeoutMs = 180_000L     // 連続送信保護タイマー(3分)

    private val totRunnable = Runnable {
        Log.w(TAG, "TOT保護発動：送信を自動停止します")
        setPttState(false)
    }

    private val usbEventReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                UsbManager.ACTION_USB_DEVICE_ATTACHED -> {
                    statusText = "USB接続検知、接続試行中..."
                    tryConnectUsb()
                }
                UsbManager.ACTION_USB_DEVICE_DETACHED -> {
                    statusText = "USBケーブルが抜かれました"
                    closeUsb()
                    mainHandler.post { setPttState(false) }
                }
            }
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        isServiceRunning = true
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        usbManager = getSystemService(Context.USB_SERVICE) as UsbManager

        val filter = IntentFilter().apply {
            addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED)
            addAction(UsbManager.ACTION_USB_DEVICE_DETACHED)
        }
        ContextCompat.registerReceiver(this, usbEventReceiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)

        statusText = "待機中（USBシリアルを検索中...）"
        tryConnectUsb()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
    }

    override fun onInterrupt() {
        mainHandler.post { setPttState(false) }
    }

    override fun onDestroy() {
        super.onDestroy()
        isServiceRunning = false
        instance = null
        try {
            unregisterReceiver(usbEventReceiver)
        } catch (_: Exception) {}
        closeUsb()
        mainHandler.removeCallbacksAndMessages(null)
    }

    fun tryConnectUsb() {
        closeUsb()
        val drivers = UsbSerialProber.getDefaultProber().findAllDrivers(usbManager)
        if (drivers.isEmpty()) {
            statusText = "USBシリアル機器が見つかりません"
            return
        }

        val driver = drivers[0]
        val device: UsbDevice = driver.device
        if (!usbManager.hasPermission(device)) {
            statusText = "USB権限がありません（設定アプリから許可してください）"
            return
        }

        val connection = usbManager.openDevice(device)
        if (connection == null) {
            statusText = "USBデバイスのオープンに失敗しました"
            return
        }

        val port = driver.ports[0]
        try {
            port.open(connection)
            port.setParameters(9600, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE)
            serialPort = port
            statusText = "接続完了: ${driver.javaClass.simpleName}"
            startPolling(port)
        } catch (e: Exception) {
            statusText = "シリアル初期化エラー: ${e.message}"
            closeUsb()
        }
    }

    private fun startPolling(port: UsbSerialPort) {
        pollingActive = true
        pollingThread = Thread {
            var lastConfirmedPtt = false
            var candidatePtt = false
            var stableCount = 0

            while (pollingActive) {
                try {
                    val targetPin = prefs.getString(KEY_TARGET_PIN, "CTS") ?: "CTS"
                    val invert = prefs.getBoolean(KEY_INVERT_LOGIC, true)

                    val rawState = when (targetPin) {
                        "DSR" -> port.getDSR()
                        "CD" -> port.getCD()
                        "RI" -> port.getRI()
                        else -> port.getCTS()
                    }
                    lastPinRawState = rawState

                    val pttSignal = if (invert) !rawState else rawState

                    // 簡易チャタリング除去（10ms × 2回連続一致で確定）
                    if (pttSignal == candidatePtt) {
                        stableCount++
                        if (stableCount >= 2 && pttSignal != lastConfirmedPtt) {
                            lastConfirmedPtt = pttSignal
                            mainHandler.post { setPttState(pttSignal) }
                        }
                    } else {
                        candidatePtt = pttSignal
                        stableCount = 1
                    }

                    Thread.sleep(10)
                } catch (e: IOException) {
                    statusText = "USB通信エラー（切断されました）"
                    mainHandler.post { setPttState(false) }
                    break
                } catch (e: UnsupportedOperationException) {
                    statusText = "選択されたピンはこの変換ICで非対応です"
                    break
                } catch (_: InterruptedException) {
                    break
                }
            }
        }.apply { start() }
    }

    private fun closeUsb() {
        pollingActive = false
        pollingThread?.interrupt()
        pollingThread = null
        try {
            serialPort?.close()
        } catch (_: Exception) {}
        serialPort = null
        lastPinRawState = null
    }

    private fun setPttState(active: Boolean) {
        if (isPttDesired == active) return
        isPttDesired = active
        if (active) {
            mainHandler.removeCallbacks(totRunnable)
            mainHandler.postDelayed(totRunnable, totTimeoutMs)
            startLongHold()
        } else {
            mainHandler.removeCallbacks(totRunnable)
            if (isHolding) {
                releaseHoldByCancel()
            }
        }
    }

    private fun startLongHold() {
        val x = prefs.getFloat(KEY_PTT_X, 540f)
        val y = prefs.getFloat(KEY_PTT_Y, 1500f)
        val path = Path().apply { moveTo(x, y) }

        // willContinue = false で最大55秒の単発ホールドを送る
        val stroke = GestureDescription.StrokeDescription(path, 0L, holdMaxDurationMs, false)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()

        isHolding = true
        val ok = dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                isHolding = false
                if (isPttDesired) {
                    // 55秒を超えてもまだピンONなら続けてホールド
                    startLongHold()
                }
            }

            override fun onCancelled(gestureDescription: GestureDescription?) {
                isHolding = false
            }
        }, mainHandler)

        if (!ok) {
            isHolding = false
        }
    }

    private fun releaseHoldByCancel() {
        isHolding = false
        // 画面最上部の中央（ステータスバー内・アプリボタンに当たらない場所）に10msの極短タップを打ち、
        // 進行中のロングタッチを強制中断（指離し相当のACTION_CANCEL）させる
        val centerX = resources.displayMetrics.widthPixels / 2f
        val cancelPath = Path().apply { moveTo(centerX, 5f) }
        val cancelStroke = GestureDescription.StrokeDescription(cancelPath, 0L, 10L, false)
        val cancelGesture = GestureDescription.Builder().addStroke(cancelStroke).build()
        dispatchGesture(cancelGesture, null, mainHandler)
    }
}