#!/usr/bin/env python3
"""
Simple OAuth2 flow for Gmail - OOB (Out of Band) mode
適合遠端 SSH 環境
"""

import os
import pickle
import sys
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def main():
    # Get OAuth2 Client credentials
    client_secrets_path = 'config/client_secrets.json'
    
    if not os.path.exists(client_secrets_path):
        print(f"錯誤：找不到 {client_secrets_path}")
        print("請先建立 OAuth Client Secret")
        sys.exit(1)
    
    import json
    with open(client_secrets_path, 'r') as f:
        secrets = json.load(f)
    
    client_id = secrets['installed']['client_id']
    client_secret = secrets['installed']['client_secret']
    
    print("=" * 60)
    print("Gmail OAuth2 認證 - OOB 模式")
    print("=" * 60)
    print()
    
    # Step 1: Get authorization URL
    flow = Flow.from_client_config(
        {'web': {'client-id': client_id, 'client-secret': client_secret}},
        scopes=SCOPES,
        redirect_uri='urn:ietf:wg:oauth:2.0:oob'
    )
    
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    print("步驟 1：複製下面的授權 URL")
    print("-" * 60)
    print(auth_url)
    print("-" * 60)
    print()
    print("步驟 2：在瀏覽器中打開上面的 URL")
    print("步驟 3：授權後，複製授權碼（authorization code）")
    print("步驟 4：貼到下面的提示")
    print()
    
    # Step 2: Get authorization code
    auth_code = input("請輸入授權碼：").strip()
    
    if not auth_code:
        print("錯誤：未輸入授權碼")
        sys.exit(1)
    
    # Step 3: Exchange code for tokens
    print("正在交換 token...")
    try:
        flow.fetch_token(authorization_response=auth_code)
        creds = flow.credentials
        
        # Step 4: Save tokens
        token_path = 'config/token.json'
        os.makedirs('config', exist_ok=True)
        
        with open(token_path, 'wb') as f:
            pickle.dump(creds, f)
        
        print()
        print("=" * 60)
        print("✓ 認證成功！")
        print("=" * 60)
        print(f"Token 已儲存到：{token_path}")
        print()
        print("下一步：測試 Gmail API")
        
        # Test API access
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        email = profile.get('emailAddress')
        
        print(f"✓ 已認證為：{email}")
        
    except Exception as e:
        print(f"錯誤：{e}")
        print()
        print("常見問題：")
        print("1. 授權碼可能包含空格，請複製整行")
        print("2. 確保 Google Cloud Console 的授權 URI 已更新")
        print("3. 嘗試重新建立 OAuth Client Secret")
        sys.exit(1)

if __name__ == '__main__':
    main()
