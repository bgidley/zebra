VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Versions"
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

Private mlngMaxVersion As Long
Private mcol As Collection
Private WithEvents moThis As ACGContainer.Container
Attribute moThis.VB_VarHelpID = -1

Private Sub Class_Initialize()
    Set mcol = New Collection
    Set moThis = New ACGContainer.Container
End Sub

Private Sub moThis_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub

Public Function Add(Optional ByVal oProcessDef As ProcessDef = Nothing, Optional ByVal lngVersion As Long = -1) As ProcessVersion
    Dim oNew As ProcessVersion
    Set oNew = New ProcessVersion
    If oProcessDef Is Nothing Then
        oProcessDef = New ProcessDef
    End If
    If lngVersion = -1 Then
        lngVersion = mlngMaxVersion + 1
    ElseIf lngVersion > mlngMaxVersion Then
        mlngMaxVersion = lngVersion
    End If
    oNew.Init oProcessDef, lngVersion, moThis
    mcol.Add oNew, "@" & lngVersion
    Set Add = oNew
End Function

Public Property Get MaxVer() As Long
    MaxVer = mlngMaxVersion
End Property

Public Property Get Item(VersionId As Long) As ProcessVersion
Attribute Item.VB_UserMemId = 0
    Set Item = mcol("@" & VersionId)
End Property

Public Property Get Count() As Long
    Count = mcol.Count
End Property

Public Property Get ItemByPos(Index As Long) As ProcessVersion
    Set ItemByPos = mcol(Index)
End Property

Public Property Get NewEnum() As IUnknown
Attribute NewEnum.VB_UserMemId = -4
Attribute NewEnum.VB_MemberFlags = "40"
    'this property allows you to enumerate
    'this collection with the For...Each syntax
    Set NewEnum = mcol.[_NewEnum]
End Property

Public Sub Remove(pv As ProcessVersion)
    mcol.Remove "@" & pv.Version
End Sub
