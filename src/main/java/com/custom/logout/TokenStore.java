package com.custom.logout;

import java.util.concurrent.ConcurrentHashMap;

public class TokenStore {
    public static ConcurrentHashMap<String, Boolean> killedTokens = new ConcurrentHashMap<>();
}
