#!/bin/bash

# 从离线下载的 packages/ 目录安装依赖（无需联网）
npm install ./packages/*.tgz --offline
echo "done"