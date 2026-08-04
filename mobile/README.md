# FitMe 原生 App

基于 Expo SDK 57、React Native 0.86 和 Expo Router 构建。Android 使用原生 Activity 与 Hermes，不包含 WebView 或开发客户端。

## 本地开发

```powershell
npm install
npm run android
```

Android 模拟器默认通过 `http://10.0.2.2:8080` 访问宿主机 Java 网关；iOS 模拟器默认使用 `http://127.0.0.1:8080`。

真机或生产构建需配置网关地址：

```powershell
$env:EXPO_PUBLIC_API_BASE_URL='https://api.example.com'
npm run android
```

## 质量检查

```powershell
npx tsc --noEmit
npx expo lint
npx expo-doctor
```

## Android Release

需要 JDK 17、Android SDK 36 和 NDK 27.1：

```powershell
$env:NODE_ENV='production'
Set-Location android
.\gradlew.bat app:assembleRelease
```

输出位于 `android/app/build/outputs/apk/release/app-release.apk`。

## 模块边界

- Java 网关：认证、商品、购物车、衣橱及统一 API；
- Python Agent：需求理解、RAG 检索、工具编排与 SSE 事件；
- 原生 App：SecureStore、原生导航、图片选择、触觉反馈、流式渲染与业务状态展示。

Agent 界面只展示真实后端事件，不生成虚假进度。
