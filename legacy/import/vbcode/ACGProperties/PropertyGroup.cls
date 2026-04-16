VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "PropertyGroup"
Attribute VB_GlobalNameSpace = False
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

Private mCol As Collection
Private WithEvents mParentContainer As Container
Attribute mParentContainer.VB_VarHelpID = -1

Private Sub Class_Initialize()
    Set mCol = New Collection
    Set mParentContainer = New Container
End Sub

Public Property Get Item(key As Variant) As Properties
Attribute Item.VB_UserMemId = 0
Attribute Item.VB_MemberFlags = "200"
    If VarType(key) = vbString Then
        Set Item = mCol(UCase$(key))
    Else
        Set Item = mCol(key)
    End If
End Property

Public Function Add(Name As String) As Properties
    Dim oNew As Properties
    Set oNew = New Properties
    oNew.Name = Name
    Set oNew.ParentContainer = mParentContainer
    mCol.Add oNew, UCase$(Name)
    Set Add = oNew
End Function

Public Property Get NewEnum() As IUnknown
Attribute NewEnum.VB_UserMemId = -4
Attribute NewEnum.VB_MemberFlags = "40"
    'this property allows you to enumerate
    'this collection with the For...Each syntax
    Set NewEnum = mCol.[_NewEnum]
End Property

Public Function Exists(GroupName As String) As Boolean
    On Error Resume Next
    Dim oProp As Properties
    Set oProp = mCol(UCase$(GroupName))
    If Err.Number <> 0 Then
        Exists = False
    Else
        Exists = True
    End If
    Err.Clear
End Function


Private Sub mParentContainer_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub
