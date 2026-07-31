export type Json
  = | string
    | number
    | boolean
    | null
    | { [key: string]: Json | undefined }
    | Json[]

export interface Database {
  public: {
    Tables: {
      users: {
        Row: {
          id: string
          email: string | null
          name: string | null
          avatar: string | null
          username: string | null
          provider: string | null
          provider_id: string | null
          created_at: string
        }
        Insert: {
          id: string
          email?: string | null
          name?: string | null
          avatar?: string | null
          username?: string | null
          provider?: string | null
          provider_id?: string | null
          created_at?: string
        }
        Update: {
          id?: string
          email?: string | null
          name?: string | null
          avatar?: string | null
          username?: string | null
          provider?: string | null
          provider_id?: string | null
          created_at?: string
        }
      }
      chats: {
        Row: {
          id: string
          title: string | null
          user_id: string
          visibility: 'public' | 'private'
          created_at: string
        }
        Insert: {
          id?: string
          title?: string | null
          user_id: string
          visibility?: 'public' | 'private'
          created_at?: string
        }
        Update: {
          id?: string
          title?: string | null
          user_id?: string
          visibility?: 'public' | 'private'
          created_at?: string
        }
      }
      messages: {
        Row: {
          id: string
          chat_id: string
          role: 'user' | 'assistant' | 'system'
          parts: Json
          created_at: string
        }
        Insert: {
          id?: string
          chat_id: string
          role: 'user' | 'assistant' | 'system'
          parts?: Json
          created_at?: string
        }
        Update: {
          id?: string
          chat_id?: string
          role?: 'user' | 'assistant' | 'system'
          parts?: Json
          created_at?: string
        }
      }
      votes: {
        Row: {
          chat_id: string
          message_id: string
          is_upvoted: boolean
        }
        Insert: {
          chat_id: string
          message_id: string
          is_upvoted: boolean
        }
        Update: {
          chat_id?: string
          message_id?: string
          is_upvoted?: boolean
        }
      }
    }
  }
}
