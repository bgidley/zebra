VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "StringTokenizer"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
Attribute VB_Ext_KEY = "SavedWithClassBuilder6" ,"Yes"
Attribute VB_Ext_KEY = "Top_Level" ,"Yes"
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private mCol As Collection
Private mfErrorParsing As Boolean

Public Function Parse(Values As String, Delimeter As String)
    Set mCol = New Collection
    Dim intCount As Integer
    Dim chPos As String * 1
    Dim intLast As Integer
    Dim intDelLen  As Integer
    Dim intValLen As Integer
    Dim fInQuotes As Boolean
    Dim strItem As String
    Dim fAddChar As Boolean
    
    intValLen = Len(Values)
    intDelLen = Len(Delimeter)
    intLast = 1
    
    For intCount = 1 To Len(Values)
        chPos = Mid$(Values, intCount, 1)
        Select Case chPos
            Case """"
                fInQuotes = Not fInQuotes
                fAddChar = True
            Case Else
                If Not fInQuotes Then
                    If StrComp(Mid$(Values, intCount, intDelLen), Delimeter, vbTextCompare) = 0 Then
                        '# found a delimeter
                        mCol.Add Trim$(strItem)
                        strItem = ""
                        fAddChar = False
                        intCount = intCount + intDelLen - 1
                        intLast = intCount + intDelLen - 1
                    Else
                        fAddChar = True
                    End If
                Else
                    fAddChar = True
                End If
                
        End Select
        If fAddChar Then strItem = strItem & chPos
    Next
    If Len(Trim$(strItem)) > 0 Then
        mCol.Add Trim$(strItem)
    End If
    mfErrorParsing = fInQuotes Or (intLast < intCount)
    
    Parse = Not mfErrorParsing
End Function

Public Property Get ParsedItems() As Collection
    Set ParsedItems = mCol
End Property

Public Property Get ErrorParsing() As Boolean
    ErrorParsing = mfErrorParsing
End Property

