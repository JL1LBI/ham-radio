package com.example.usbserialptt // ← ご自身のパッケージ名に合わせてください

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.hoho.android.usbserial.driver.UsbSerialProber

class MainActivity : AppCompatActivity() {

    companion object {
        private const val ACTION_USB_PERMISSION = "com.example.usbserialptt.USB_PERMISSION"
    }

    private lateinit var txtStatus: TextView
    private val uiHandler = Handler(Looper.getMainLooper())
    private val pins = listOf("CTS", "DSR", "CD", "RI")

    private val permissionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == ACTION_USB_PERMISSION) {
                val granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                if (granted) {
                    Toast.makeText(context, "USB権限が許可されました", Toast.LENGTH_SHORT).show()
                    PttAccessibilityService.instance?.tryConnectUsb()
                } else {
                    Toast.makeText(context, "USB権限が拒否されました", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private val statusUpdater = object : Runnable {
        override fun run() {
            val running = if (PttAccessibilityService.isServiceRunning) "稼働中" else "停止中"
            val pinState = PttAccessibilityService.lastPinRawState?.toString() ?: "未取得"
            txtStatus.text = "サービス: $running\nUSB状態: ${PttAccessibilityService.statusText}\nピン生値: $pinState"
            uiHandler.postDelayed(this, 200)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val prefs = getSharedPreferences(PttAccessibilityService.PREFS_NAME, MODE_PRIVATE)
        txtStatus = findViewById(R.id.txtStatus)
        val editX = findViewById<EditText>(R.id.editX)
        val editY = findViewById<EditText>(R.id.editY)
        val spinnerPin = findViewById<Spinner>(R.id.spinnerPin)
        val chkInvert = findViewById<CheckBox>(R.id.chkInvert)

        spinnerPin.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, pins)

        // 保存値の読み込み
        editX.setText(prefs.getFloat(PttAccessibilityService.KEY_PTT_X, 540f).toString())
        editY.setText(prefs.getFloat(PttAccessibilityService.KEY_PTT_Y, 1500f).toString())
        val savedPin = prefs.getString(PttAccessibilityService.KEY_TARGET_PIN, "CTS")
        spinnerPin.setSelection(pins.indexOf(savedPin).coerceAtLeast(0))
        chkInvert.isChecked = prefs.getBoolean(PttAccessibilityService.KEY_INVERT_LOGIC, true)

        findViewById<Button>(R.id.btnSave).setOnClickListener {
            val x = editX.text.toString().toFloatOrNull() ?: 540f
            val y = editY.text.toString().toFloatOrNull() ?: 1500f
            prefs.edit()
                .putFloat(PttAccessibilityService.KEY_PTT_X, x)
                .putFloat(PttAccessibilityService.KEY_PTT_Y, y)
                .putString(PttAccessibilityService.KEY_TARGET_PIN, pins[spinnerPin.selectedItemPosition])
                .putBoolean(PttAccessibilityService.KEY_INVERT_LOGIC, chkInvert.isChecked)
                .apply()
            Toast.makeText(this, "設定を保存しました", Toast.LENGTH_SHORT).show()
        }

        findViewById<Button>(R.id.btnUsbPermission).setOnClickListener {
            requestUsbPermission()
        }

        findViewById<Button>(R.id.btnOpenAccessibility).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }

        val filter = IntentFilter(ACTION_USB_PERMISSION)
        ContextCompat.registerReceiver(this, permissionReceiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
    }

    private fun requestUsbPermission() {
        val usbManager = getSystemService(Context.USB_SERVICE) as UsbManager
        val drivers = UsbSerialProber.getDefaultProber().findAllDrivers(usbManager)
        if (drivers.isEmpty()) {
            Toast.makeText(this, "USBシリアルケーブルが見つかりません", Toast.LENGTH_SHORT).show()
            return
        }
        val device = drivers[0].device
        if (usbManager.hasPermission(device)) {
            PttAccessibilityService.instance?.tryConnectUsb()
            Toast.makeText(this, "すでに権限あり・再接続を試行します", Toast.LENGTH_SHORT).show()
            return
        }

        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            PendingIntent.FLAG_MUTABLE
        } else {
            0
        }
        // Android 14+で安全に権限応答を受け取るためsetPackageを指定
        val intent = Intent(ACTION_USB_PERMISSION).setPackage(packageName)
        val pendingIntent = PendingIntent.getBroadcast(this, 0, intent, flags)
        usbManager.requestPermission(device, pendingIntent)
    }

    override fun onResume() {
        super.onResume()
        uiHandler.post(statusUpdater)
    }

    override fun onPause() {
        super.onPause()
        uiHandler.removeCallbacks(statusUpdater)
    }

    override fun onDestroy() {
        super.onDestroy()
        unregisterReceiver(permissionReceiver)
    }
}