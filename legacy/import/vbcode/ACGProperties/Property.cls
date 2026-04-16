VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Property"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
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

Public Enum enPropertyTypes
    ptString = 1
    ptFile = 2
    ptBoolean = 3
    ptInteger = 4
End Enum

Private mParent As Container

Public Name As String
Private mValue As Variant
Public PropertyType As enPropertyTypes
Public Locked As Boolean

Public Property Get Properties() As Properties
    Set Properties = mParent.GetParent()
End Property

Friend Property Set ParentContainer(v As Container)
    Set mParent = v
End Property

Public Property Get Value() As Variant
    If IsObject(mValue) Then
        Set Value = mValue
    Else
        Value = mValue
    End If
End Property

Public Property Let Value(v As Variant)
    Select Case PropertyType
        Case ptBoolean
            mValue = LenientBool(v)
        Case Else
            mValue = v
    End Select
End Property

Public Property Set Value(v As Variant)
    Set mValue = v
End Property
