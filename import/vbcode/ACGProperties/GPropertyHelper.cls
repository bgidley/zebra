VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "GPropertyHelper"
Attribute VB_GlobalNameSpace = True
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
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

Public Function StringToPropType(TypeString As String) As ACGProperties.enPropertyTypes
    Select Case LCase$(TypeString)
        Case "string"
            StringToPropType = ptString
        Case "boolean"
            StringToPropType = ptBoolean
        Case "file"
            StringToPropType = ptFile
        Case "integer"
            StringToPropType = ptInteger
        Case Else
            '# return string
            StringToPropType = ptString
    End Select
End Function

Public Function PropTypeToString(PropType As ACGProperties.enPropertyTypes) As String
    Select Case PropType
        Case ptString
            PropTypeToString = "string"
        Case ptBoolean
            PropTypeToString = "boolean"
        Case ptFile
            PropTypeToString = "file"
        Case ptInteger
            PropTypeToString = "integer"
        Case Else
            '# return string
            PropTypeToString = "string"
    End Select
End Function

Public Function LenientBool(Value As Variant) As Boolean
    LenientBool = basProperties.LenientBool(Value)
End Function

